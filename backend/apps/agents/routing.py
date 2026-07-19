from uuid import UUID

from django.contrib.auth.models import User
from langchain_core.messages import AnyMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from pydantic import JsonValue

from apps.agents.context import RuntimeContext
from apps.agents.execution import GraphExecutionLimits
from apps.agents.state import AppState, WorkflowName
from apps.agents.triggers import TriggerEnvelope, TriggerType

type RouteTarget = WorkflowName

TRIGGER_ROUTES: dict[TriggerType, RouteTarget] = {
    "user_message": "time_steward_agent",
    "manual_briefing": "briefing_workflow",
    "scheduled_briefing": "briefing_workflow",
    "reminder_due": "reminder_dispatcher",
    "calendar_webhook": "calendar_sync_workflow",
}


class InvalidTriggerPayloadError(ValueError):
    pass


class MissingConversationError(ValueError):
    pass


def route_trigger(state: AppState) -> Command[RouteTarget]:
    """Update the active route and deterministically select one workflow node."""

    trigger_type = state.get("trigger_type")
    if trigger_type is None:
        raise ValueError("AppState.trigger_type is required before routing")
    destination = TRIGGER_ROUTES[trigger_type]
    return Command(update={"active_workflow": destination}, goto=destination)


def state_from_trigger(envelope: TriggerEnvelope) -> AppState:
    messages: list[AnyMessage] = []
    if envelope.trigger_type == "user_message":
        messages = [HumanMessage(content=required_payload_string(envelope.payload, "message"))]
    elif envelope.trigger_type in {"manual_briefing", "scheduled_briefing"}:
        synthetic_message = envelope.payload.get("synthetic_message")
        if isinstance(synthetic_message, str) and synthetic_message.strip():
            messages = [
                HumanMessage(
                    content=synthetic_message.strip(),
                    additional_kwargs={
                        "synthetic": True,
                        "source": envelope.trigger_type,
                    },
                )
            ]

    state: AppState = {
        "messages": messages,
        "trigger_type": envelope.trigger_type,
        "trigger_payload": dict(envelope.payload),
        "operation_id": str(envelope.operation_id),
    }
    briefing_definition_id = envelope.payload.get("briefing_definition_id")
    if briefing_definition_id is not None:
        if not isinstance(briefing_definition_id, str) or not briefing_definition_id.strip():
            raise InvalidTriggerPayloadError(
                "payload.briefing_definition_id must be a non-empty string"
            )
    return state


def runtime_context_from_trigger(
    envelope: TriggerEnvelope,
    *,
    request_id: str,
    timezone: str,
    locale: str,
    read_only: bool = False,
    actor: User | None = None,
    agent_run_id: str | None = None,
) -> RuntimeContext:
    return RuntimeContext(
        user_id=str(envelope.user_id),
        request_id=request_id,
        timezone=timezone,
        locale=locale,
        current_datetime=envelope.triggered_at,
        trigger_type=envelope.trigger_type,
        conversation_id=(
            str(envelope.conversation_id) if envelope.conversation_id is not None else None
        ),
        agent_run_id=agent_run_id,
        read_only=read_only,
        actor=actor,
    )


def checkpoint_thread_id(envelope: TriggerEnvelope) -> str | None:
    if envelope.trigger_type == "reminder_due":
        return None
    if envelope.conversation_id is not None:
        return str(envelope.conversation_id)
    if envelope.trigger_type == "user_message":
        raise MissingConversationError("user_message requires conversation_id for checkpointing")
    return str(envelope.operation_id)


def graph_config_from_trigger(
    envelope: TriggerEnvelope,
    context: RuntimeContext,
    *,
    limits: GraphExecutionLimits | None = None,
) -> RunnableConfig:
    thread_id = checkpoint_thread_id(envelope)
    config: RunnableConfig = {
        "metadata": {
            "operation_id": str(envelope.operation_id),
            "request_id": context.request_id,
            "user_id": context.user_id,
            "trigger_type": envelope.trigger_type,
        }
    }
    if thread_id is not None:
        config = graph_config_for_thread(
            thread_id,
            request_id=context.request_id,
            user_id=context.user_id,
            operation_id=str(envelope.operation_id),
            trigger_type=envelope.trigger_type,
        )
    return limits.apply(config) if limits is not None else config


def graph_config_for_thread(
    thread_id: str,
    *,
    request_id: str,
    user_id: str | None = None,
    operation_id: str | None = None,
    trigger_type: TriggerType | None = None,
    limits: GraphExecutionLimits | None = None,
) -> RunnableConfig:
    normalized_thread_id = thread_id.strip()
    normalized_request_id = request_id.strip()
    if not normalized_thread_id:
        raise ValueError("thread_id cannot be empty")
    if not normalized_request_id:
        raise ValueError("request_id cannot be empty")
    metadata: dict[str, str] = {"request_id": normalized_request_id}
    for key, value in (
        ("user_id", user_id),
        ("operation_id", operation_id),
        ("trigger_type", trigger_type),
    ):
        if value is not None:
            normalized_value = value.strip()
            if not normalized_value:
                raise ValueError(f"{key} cannot be empty")
            metadata[key] = normalized_value
    config: RunnableConfig = {
        "configurable": {"thread_id": normalized_thread_id},
        "metadata": metadata,
    }
    return limits.apply(config) if limits is not None else config


def ensure_context_matches_trigger(
    envelope: TriggerEnvelope,
    context: RuntimeContext,
) -> None:
    expected = (
        ("user_id", str(envelope.user_id), context.user_id),
        ("trigger_type", envelope.trigger_type, context.trigger_type),
        (
            "conversation_id",
            str(envelope.conversation_id) if envelope.conversation_id is not None else None,
            context.conversation_id,
        ),
    )
    for field_name, envelope_value, context_value in expected:
        if envelope_value != context_value:
            raise ValueError(f"TriggerEnvelope and RuntimeContext disagree on {field_name}")


def required_payload_uuid(payload: dict[str, JsonValue], key: str) -> UUID:
    value = required_payload_string(payload, key)
    try:
        return UUID(value)
    except ValueError as exc:
        raise InvalidTriggerPayloadError(f"payload.{key} must be a UUID") from exc


def required_payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidTriggerPayloadError(f"payload.{key} must be a non-empty string")
    return value.strip()
