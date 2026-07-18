import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Literal
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.exceptions import ImproperlyConfigured
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, StateGraph
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command, interrupt

from apps.agents.context import RuntimeContext
from apps.agents.execution import (
    GraphExecutionLimits,
    GraphStepLimitExceededError,
    get_graph_execution_limits,
)
from apps.agents.outer_graph import (
    NoPendingInterruptError,
    OuterGraphNodes,
    StatelessTriggerResumeError,
    build_outer_graph_runtime,
)
from apps.agents.routing import (
    graph_config_from_trigger,
    runtime_context_from_trigger,
)
from apps.agents.state import AppState
from apps.agents.triggers import TriggerEnvelope


def make_user_envelope() -> TriggerEnvelope:
    return TriggerEnvelope(
        trigger_type="user_message",
        user_id=str(uuid4()),
        operation_id=uuid4(),
        conversation_id=uuid4(),
        payload={"message": "pause this run"},
        triggered_at=datetime(2026, 7, 17, 8, tzinfo=UTC),
    )


def make_context(
    envelope: TriggerEnvelope,
    *,
    request_id: str | None = None,
) -> RuntimeContext:
    return RuntimeContext(
        user_id=str(envelope.user_id),
        request_id=request_id or str(uuid4()),
        timezone="UTC",
        locale="en-US",
        current_datetime=datetime(2026, 7, 17, 9, tzinfo=UTC),
        trigger_type=envelope.trigger_type,
        conversation_id=(
            str(envelope.conversation_id) if envelope.conversation_id is not None else None
        ),
    )


def unreachable_workflow(state: AppState) -> dict[str, str]:
    raise AssertionError(f"Unexpected route for {state['trigger_type']}")


def test_interrupt_snapshot_and_command_resume_use_same_persisted_thread() -> None:
    replay_markers: list[str] = []

    def approval_workflow(state: AppState) -> dict[str, object]:
        replay_markers.append(state["operation_id"])
        decision = interrupt(
            {
                "kind": "approval",
                "operation_id": state["operation_id"],
            }
        )
        assert isinstance(decision, dict)
        return {
            "messages": [AIMessage(content="approved" if decision.get("approved") else "rejected")]
        }

    envelope = make_user_envelope()
    thread_id = str(envelope.conversation_id)
    runtime = build_outer_graph_runtime(
        OuterGraphNodes(
            time_steward_agent=approval_workflow,
            briefing_workflow=unreachable_workflow,
            calendar_sync_workflow=unreachable_workflow,
        ),
        checkpointer=InMemorySaver(),
        store=InMemoryStore(),
        limits=GraphExecutionLimits(recursion_limit=20, max_concurrency=2),
    )

    initial_result = runtime.invoke(envelope, make_context(envelope))
    pending = runtime.pending_interrupts(thread_id)

    assert len(initial_result["messages"]) == 1
    assert len(pending) == 1
    assert pending[0].value == {
        "kind": "approval",
        "operation_id": str(envelope.operation_id),
    }

    resumed = runtime.resume(
        thread_id=thread_id,
        resume_value={"approved": True},
        context=make_context(envelope, request_id=str(uuid4())),
    )

    assert resumed["messages"][-1].content == "approved"
    assert runtime.pending_interrupts(thread_id) == ()
    assert replay_markers == [str(envelope.operation_id), str(envelope.operation_id)]

    with pytest.raises(NoPendingInterruptError, match="no pending interrupt"):
        runtime.resume(
            thread_id=thread_id,
            resume_value={"approved": True},
            context=make_context(envelope, request_id=str(uuid4())),
        )


def test_async_interrupt_inspection_and_resume_use_native_async_api() -> None:
    def approval_workflow(state: AppState) -> dict[str, object]:
        approved = interrupt({"kind": "async-approval"})
        return {"messages": [AIMessage(content="approved" if approved is True else "rejected")]}

    async def scenario() -> None:
        envelope = make_user_envelope()
        thread_id = str(envelope.conversation_id)
        runtime = build_outer_graph_runtime(
            OuterGraphNodes(
                time_steward_agent=approval_workflow,
                briefing_workflow=unreachable_workflow,
                calendar_sync_workflow=unreachable_workflow,
            ),
            checkpointer=InMemorySaver(),
            store=InMemoryStore(),
            limits=GraphExecutionLimits(recursion_limit=20, max_concurrency=2),
        )

        await runtime.ainvoke(envelope, make_context(envelope))
        pending = await runtime.apending_interrupts(thread_id)
        assert len(pending) == 1

        resumed = await runtime.aresume(
            thread_id=thread_id,
            resume_value=True,
            context=make_context(envelope, request_id=str(uuid4())),
        )
        assert resumed["messages"][-1].content == "approved"
        assert await runtime.apending_interrupts(thread_id) == ()

    asyncio.run(scenario())


def test_reminder_runs_cannot_enter_resume_path() -> None:
    envelope = TriggerEnvelope(
        trigger_type="reminder_due",
        user_id=str(uuid4()),
        operation_id=uuid4(),
        payload={"reminder_id": str(uuid4())},
        triggered_at=datetime(2026, 7, 17, 8, tzinfo=UTC),
    )
    runtime = build_outer_graph_runtime(
        OuterGraphNodes(
            time_steward_agent=unreachable_workflow,
            briefing_workflow=unreachable_workflow,
            calendar_sync_workflow=unreachable_workflow,
        ),
        checkpointer=InMemorySaver(),
        store=InMemoryStore(),
        limits=GraphExecutionLimits(recursion_limit=20, max_concurrency=2),
    )

    with pytest.raises(StatelessTriggerResumeError, match="cannot be resumed"):
        runtime.resume(
            thread_id=str(envelope.operation_id),
            resume_value=True,
            context=runtime_context_from_trigger(
                envelope,
                request_id=str(uuid4()),
                timezone="UTC",
                locale="en-US",
            ),
        )


def test_non_terminating_subgraph_maps_recursion_error_to_safe_domain_error() -> None:
    def loop_forever(state: AppState) -> Command[Literal["loop_forever"]]:
        return Command(goto="loop_forever")

    subgraph_builder = StateGraph(AppState)
    subgraph_builder.add_node("loop_forever", loop_forever)
    subgraph_builder.add_edge(START, "loop_forever")
    looping_subgraph = subgraph_builder.compile()
    limits = GraphExecutionLimits(recursion_limit=7, max_concurrency=1)
    runtime = build_outer_graph_runtime(
        OuterGraphNodes(
            time_steward_agent=looping_subgraph,
            briefing_workflow=unreachable_workflow,
            calendar_sync_workflow=unreachable_workflow,
        ),
        checkpointer=InMemorySaver(),
        store=InMemoryStore(),
        limits=limits,
    )
    envelope = make_user_envelope()

    with pytest.raises(GraphStepLimitExceededError) as error:
        runtime.invoke(envelope, make_context(envelope))

    assert error.value.recursion_limit == 7
    assert "7-step" in str(error.value)


def test_remaining_steps_allows_subgraph_to_finish_before_hard_limit() -> None:
    def bounded_loop(state: AppState) -> dict[str, object]:
        if state["remaining_steps"] <= 2:
            return {"workflow_result": {"status": "best-effort-safe-exit"}}
        return {}

    def continue_or_end(state: AppState) -> Literal["bounded_loop", "__end__"]:
        return "__end__" if "workflow_result" in state else "bounded_loop"

    subgraph_builder = StateGraph(AppState)
    subgraph_builder.add_node("bounded_loop", bounded_loop)
    subgraph_builder.add_edge(START, "bounded_loop")
    subgraph_builder.add_conditional_edges("bounded_loop", continue_or_end)
    bounded_subgraph = subgraph_builder.compile()
    runtime = build_outer_graph_runtime(
        OuterGraphNodes(
            time_steward_agent=bounded_subgraph,
            briefing_workflow=unreachable_workflow,
            calendar_sync_workflow=unreachable_workflow,
        ),
        checkpointer=InMemorySaver(),
        store=InMemoryStore(),
        limits=GraphExecutionLimits(recursion_limit=10, max_concurrency=1),
    )
    envelope = make_user_envelope()

    result = runtime.invoke(envelope, make_context(envelope))

    assert result["workflow_result"] == {"status": "best-effort-safe-exit"}


def test_graph_limits_are_top_level_config_and_validate_settings() -> None:
    envelope = make_user_envelope()
    limits = GraphExecutionLimits(recursion_limit=30, max_concurrency=3)

    config = graph_config_from_trigger(envelope, make_context(envelope), limits=limits)

    assert config["recursion_limit"] == 30
    assert config["max_concurrency"] == 3
    assert "recursion_limit" not in config["configurable"]
    assert config["configurable"] == {
        "thread_id": str(envelope.conversation_id),
    }

    with pytest.raises(ValueError, match="recursion_limit"):
        GraphExecutionLimits(recursion_limit=0, max_concurrency=1)

    invalid_config = SimpleNamespace(
        graph=SimpleNamespace(recursion_limit="invalid", max_concurrency=1)
    )
    with (
        patch("apps.agents.execution.get_agent_config", return_value=invalid_config),
        pytest.raises(ImproperlyConfigured, match="execution limit"),
    ):
        get_graph_execution_limits()
