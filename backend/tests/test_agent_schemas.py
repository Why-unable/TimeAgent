from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from langchain.agents import AgentState
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from pydantic import ValidationError

from apps.agents.context import RuntimeContext
from apps.agents.state import AppState
from apps.agents.triggers import TriggerEnvelope
from common.time import InvalidTimezoneError, NaiveDateTimeError


def test_trigger_envelope_validates_and_serializes_transport_data() -> None:
    user_id = uuid4()
    operation_id = uuid4()
    conversation_id = uuid4()

    envelope = TriggerEnvelope.model_validate(
        {
            "trigger_type": "scheduled_briefing",
            "user_id": str(user_id),
            "operation_id": str(operation_id),
            "conversation_id": str(conversation_id),
            "payload": {"briefing_definition_id": str(uuid4()), "sections": ["today"]},
            "triggered_at": "2026-07-15T08:00:00+08:00",
        }
    )

    assert envelope.user_id == user_id
    assert envelope.operation_id == operation_id
    assert envelope.conversation_id == conversation_id
    assert envelope.triggered_at == datetime(2026, 7, 15, tzinfo=UTC)
    assert TriggerEnvelope.model_validate_json(envelope.model_dump_json()) == envelope


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("trigger_type", "unknown"),
        ("user_id", "not-a-uuid"),
        ("triggered_at", "2026-07-15T00:00:00"),
    ],
)
def test_trigger_envelope_rejects_invalid_boundary_data(field: str, value: str) -> None:
    data: dict[str, object] = {
        "trigger_type": "user_message",
        "user_id": str(uuid4()),
        "operation_id": str(uuid4()),
        "conversation_id": None,
        "payload": {"message": "hello"},
        "triggered_at": "2026-07-15T00:00:00Z",
    }
    data[field] = value

    with pytest.raises(ValidationError):
        TriggerEnvelope.model_validate(data)


def test_trigger_envelope_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        TriggerEnvelope.model_validate(
            {
                "trigger_type": "user_message",
                "user_id": str(uuid4()),
                "operation_id": str(uuid4()),
                "payload": {"message": "hello"},
                "triggered_at": "2026-07-15T00:00:00Z",
                "unexpected": True,
            }
        )


def test_runtime_context_validates_timezone_and_normalizes_current_time() -> None:
    context = RuntimeContext(
        user_id=str(uuid4()),
        request_id=str(uuid4()),
        timezone="Asia/Shanghai",
        locale="zh-CN",
        current_datetime=datetime(
            2026,
            7,
            15,
            8,
            tzinfo=timezone(timedelta(hours=8)),
        ),
        trigger_type="user_message",
    )

    assert context.current_datetime == datetime(2026, 7, 15, tzinfo=UTC)
    assert context.read_only is False

    with pytest.raises(InvalidTimezoneError):
        RuntimeContext(
            user_id=str(uuid4()),
            request_id=str(uuid4()),
            timezone="Invalid/Timezone",
            locale="zh-CN",
            current_datetime=datetime(2026, 7, 15, tzinfo=UTC),
            trigger_type="user_message",
        )

    with pytest.raises(NaiveDateTimeError):
        RuntimeContext(
            user_id=str(uuid4()),
            request_id=str(uuid4()),
            timezone="UTC",
            locale="en-US",
            current_datetime=datetime(2026, 7, 15),
            trigger_type="user_message",
        )


def test_app_state_and_runtime_context_use_native_langgraph_boundaries() -> None:
    context = RuntimeContext(
        user_id=str(uuid4()),
        request_id=str(uuid4()),
        timezone="UTC",
        locale="en-US",
        current_datetime=datetime(2026, 7, 15, tzinfo=UTC),
        trigger_type="user_message",
    )

    def read_context(
        state: AppState,
        runtime: Runtime[RuntimeContext],
    ) -> dict[str, object]:
        assert state["trigger_type"] == runtime.context.trigger_type
        return {
            "active_workflow": "time_steward_agent",
            "messages": [AIMessage(content=runtime.context.user_id)],
        }

    builder = StateGraph(AppState, context_schema=RuntimeContext)
    builder.add_node("read_context", read_context)
    builder.add_edge(START, "read_context")
    builder.add_edge("read_context", END)
    graph = builder.compile()

    result = graph.invoke(
        {
            "messages": [HumanMessage(content="hello")],
            "trigger_type": "user_message",
            "operation_id": str(uuid4()),
        },
        context=context,
    )

    assert result["active_workflow"] == "time_steward_agent"
    assert result["messages"][-1].content == context.user_id
    assert "current_datetime" not in result
    assert "timezone" not in AppState.__annotations__
    assert set(AppState.__annotations__) - set(AgentState.__annotations__) == {
        "trigger_type",
        "trigger_payload",
        "operation_id",
        "active_workflow",
        "workflow_result",
        "remaining_steps",
    }


def test_app_state_inherits_additive_agent_message_history() -> None:
    tool_call_id = "call-1"

    def finish_tool_call(_: AppState) -> dict[str, Any]:
        return {
            "messages": [
                ToolMessage(content="tool-complete", tool_call_id=tool_call_id),
                AIMessage(content="final-answer"),
            ]
        }

    builder = StateGraph(AppState)
    builder.add_node("finish_tool_call", RunnableLambda(finish_tool_call))
    builder.add_edge(START, "finish_tool_call")
    builder.add_edge("finish_tool_call", END)
    graph = builder.compile()

    result = graph.invoke(
        {
            "messages": [
                HumanMessage(content="use the tool"),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "test_tool",
                            "args": {},
                            "id": tool_call_id,
                            "type": "tool_call",
                        }
                    ],
                ),
            ],
            "trigger_type": "user_message",
            "operation_id": str(uuid4()),
        }
    )

    assert [type(message) for message in result["messages"]] == [
        HumanMessage,
        AIMessage,
        ToolMessage,
        AIMessage,
    ]
    assert result["messages"][-1].content == "final-answer"
