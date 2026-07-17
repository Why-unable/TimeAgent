from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from apps.agents.context import RuntimeContext
from apps.agents.outer_graph import (
    OuterGraphNodes,
    RuntimeContextMismatchError,
    build_outer_graph,
    build_outer_graph_runtime,
)
from apps.agents.routing import (
    InvalidTriggerPayloadError,
    MissingConversationError,
    checkpoint_thread_id,
    graph_config_from_trigger,
    runtime_context_from_trigger,
    state_from_trigger,
)
from apps.agents.state import AppState
from apps.agents.triggers import TriggerEnvelope, TriggerType

type NonReminderTrigger = Literal[
    "user_message",
    "manual_briefing",
    "scheduled_briefing",
    "calendar_webhook",
]


@dataclass(slots=True)
class WorkflowRecorder:
    calls: list[str] = field(default_factory=list)

    def time_steward_agent(self, state: AppState) -> dict[str, object]:
        self.calls.append("time_steward_agent")
        assert state["messages"]
        return {"messages": [AIMessage(content="time-steward-complete")]}

    def briefing_workflow(self, state: AppState) -> dict[str, object]:
        self.calls.append("briefing_workflow")
        assert state["trigger_type"] in {"manual_briefing", "scheduled_briefing"}
        return {"workflow_result": {"summary": "briefing-complete"}}

    def calendar_sync_workflow(self, state: AppState) -> dict[str, object]:
        self.calls.append("calendar_sync_workflow")
        assert state["trigger_type"] == "calendar_webhook"
        return {"workflow_result": {"summary": "calendar-sync-complete"}}

    def nodes(self) -> OuterGraphNodes:
        return OuterGraphNodes(
            time_steward_agent=self.time_steward_agent,
            briefing_workflow=self.briefing_workflow,
            calendar_sync_workflow=self.calendar_sync_workflow,
        )


def make_envelope(
    trigger_type: TriggerType,
    *,
    payload: dict[str, object] | None = None,
    conversation_id: UUID | None = None,
) -> TriggerEnvelope:
    return TriggerEnvelope.model_validate(
        {
            "trigger_type": trigger_type,
            "user_id": str(uuid4()),
            "operation_id": str(uuid4()),
            "conversation_id": str(conversation_id) if conversation_id else None,
            "payload": payload or {},
            "triggered_at": "2026-07-17T08:00:00Z",
        }
    )


def invoke_context(envelope: TriggerEnvelope) -> RuntimeContext:
    return runtime_context_from_trigger(
        envelope,
        request_id=str(uuid4()),
        timezone="Asia/Shanghai",
        locale="zh-CN",
    )


@pytest.mark.parametrize(
    ("trigger_type", "payload", "conversation_id", "expected_node", "expected_response"),
    [
        (
            "user_message",
            {"message": "What is on my schedule?"},
            uuid4(),
            "time_steward_agent",
            "time-steward-complete",
        ),
        (
            "manual_briefing",
            {"briefing_definition_id": str(uuid4())},
            None,
            "briefing_workflow",
            "briefing-complete",
        ),
        (
            "scheduled_briefing",
            {"briefing_definition_id": str(uuid4())},
            None,
            "briefing_workflow",
            "briefing-complete",
        ),
        (
            "calendar_webhook",
            {"provider": "google", "resource_id": "resource-1"},
            None,
            "calendar_sync_workflow",
            "calendar-sync-complete",
        ),
    ],
)
def test_non_reminder_triggers_route_to_exactly_one_persistent_workflow(
    trigger_type: NonReminderTrigger,
    payload: dict[str, object],
    conversation_id: UUID | None,
    expected_node: str,
    expected_response: str,
) -> None:
    recorder = WorkflowRecorder()
    checkpointer = InMemorySaver()
    runtime = build_outer_graph_runtime(
        recorder.nodes(),
        checkpointer=checkpointer,
        store=InMemoryStore(),
    )
    envelope = make_envelope(
        trigger_type,
        payload=payload,
        conversation_id=conversation_id,
    )

    result = runtime.invoke(envelope, invoke_context(envelope))

    assert result["active_workflow"] == expected_node
    if expected_node == "time_steward_agent":
        assert result["messages"][-1].content == expected_response
    else:
        assert result["workflow_result"]["summary"] == expected_response
    assert recorder.calls == [expected_node]
    thread_id = checkpoint_thread_id(envelope)
    assert thread_id is not None
    assert checkpointer.get_tuple({"configurable": {"thread_id": thread_id}}) is not None


def test_reminder_trigger_uses_real_dispatcher_node_without_checkpoint_or_agent() -> None:
    recorder = WorkflowRecorder()
    checkpointer = InMemorySaver()
    runtime = build_outer_graph_runtime(
        recorder.nodes(),
        checkpointer=checkpointer,
        store=InMemoryStore(),
    )
    reminder_id = uuid4()
    envelope = make_envelope(
        "reminder_due",
        payload={"reminder_id": str(reminder_id)},
    )

    with patch(
        "apps.agents.outer_graph.ReminderDispatcher.send_reminder",
        return_value=True,
    ) as send_reminder:
        result = runtime.invoke(envelope, invoke_context(envelope))

    send_reminder.assert_called_once_with(
        reminder_id,
        now=datetime(2026, 7, 17, 8, tzinfo=UTC),
    )
    assert result["active_workflow"] == "reminder_dispatcher"
    assert result["workflow_result"] == {
        "workflow": "reminder_dispatcher",
        "reminder_id": str(reminder_id),
        "delivered": True,
    }
    assert recorder.calls == []
    assert list(checkpointer.list(None)) == []
    config = graph_config_from_trigger(envelope, invoke_context(envelope))
    assert "configurable" not in config
    assert config["metadata"]["operation_id"] == str(envelope.operation_id)


def test_outer_graph_declares_all_command_destinations_in_topology() -> None:
    graph = build_outer_graph(WorkflowRecorder().nodes())
    drawable = graph.get_graph()

    assert {
        "validate_runtime_context",
        "route_by_trigger",
        "time_steward_agent",
        "briefing_workflow",
        "reminder_dispatcher",
        "calendar_sync_workflow",
    }.issubset(drawable.nodes)
    route_targets = {
        edge.target
        for edge in drawable.edges
        if edge.source == "route_by_trigger" and edge.conditional
    }
    assert route_targets == {
        "time_steward_agent",
        "briefing_workflow",
        "reminder_dispatcher",
        "calendar_sync_workflow",
    }


def test_trigger_adapter_keeps_raw_payload_and_runtime_data_separate() -> None:
    conversation_id = uuid4()
    envelope = make_envelope(
        "user_message",
        payload={"message": "hello", "client_metadata": {"source": "web"}},
        conversation_id=conversation_id,
    )

    state = state_from_trigger(envelope)
    context = invoke_context(envelope)

    assert state["trigger_payload"] == envelope.payload
    assert state["operation_id"] == str(envelope.operation_id)
    assert state["messages"][0].content == "hello"
    assert "timezone" not in state
    assert "request_id" not in state
    assert "conversation_id" not in state
    assert context.timezone == "Asia/Shanghai"
    assert context.conversation_id == str(conversation_id)
    config = graph_config_from_trigger(envelope, context)
    assert config["configurable"] == {"thread_id": str(conversation_id)}
    assert config["metadata"] == {
        "operation_id": str(envelope.operation_id),
        "request_id": context.request_id,
        "user_id": str(envelope.user_id),
        "trigger_type": "user_message",
    }


def test_user_message_requires_message_and_conversation() -> None:
    missing_message = make_envelope("user_message", conversation_id=uuid4())
    with pytest.raises(InvalidTriggerPayloadError, match="payload.message"):
        state_from_trigger(missing_message)

    missing_conversation = make_envelope(
        "user_message",
        payload={"message": "hello"},
    )
    with pytest.raises(MissingConversationError, match="conversation_id"):
        graph_config_from_trigger(
            missing_conversation,
            invoke_context(missing_conversation),
        )


def test_runtime_context_mismatch_stops_before_workflow_routing() -> None:
    recorder = WorkflowRecorder()
    graph = build_outer_graph(recorder.nodes())
    envelope = make_envelope(
        "user_message",
        payload={"message": "hello"},
        conversation_id=uuid4(),
    )
    context = invoke_context(envelope)
    mismatched_state = state_from_trigger(envelope)
    mismatched_state["trigger_type"] = "manual_briefing"

    with pytest.raises(RuntimeContextMismatchError, match="trigger_type"):
        graph.invoke(mismatched_state, context=context)

    assert recorder.calls == []
