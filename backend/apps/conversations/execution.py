from datetime import UTC, datetime
from typing import Any, cast

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk

from apps.agents.agents.time_steward import build_time_steward_agent
from apps.agents.memory.persistence import open_langgraph_persistence
from apps.agents.outer_graph import OuterGraphNodes, build_outer_graph_runtime
from apps.agents.routing import runtime_context_from_trigger
from apps.agents.state import AppState
from apps.agents.triggers import TriggerEnvelope
from apps.conversations.models import AgentRun, AgentRunStatus
from apps.conversations.services import AgentRunService
from apps.preferences.services import UserPreferenceService


class AgentRunCancelled(RuntimeError):
    pass


def _unavailable_workflow(state: AppState) -> dict[str, Any]:
    return {
        "workflow_result": {
            "available": False,
            "workflow": state.get("active_workflow", "future_workflow"),
        }
    }


def execute_agent_run(
    run: AgentRun,
    *,
    actor: User,
    model: BaseChatModel | None = None,
    now: datetime | None = None,
    task_id: str | None = None,
) -> AgentRun:
    """Execute one persisted chat run through the real Outer Graph."""

    if run.status in {
        AgentRunStatus.COMPLETED,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
    }:
        return run
    claimed = AgentRunService.claim_for_execution(run, task_id=task_id)
    if claimed is None:
        return AgentRun.objects.get(pk=run.pk)
    run = claimed

    preference = UserPreferenceService.get_for_user(actor)
    timezone_name = preference.timezone if preference else settings.DEFAULT_USER_TIMEZONE
    locale = preference.locale if preference else settings.DEFAULT_USER_LOCALE
    current_time = (now or timezone.now()).astimezone(UTC)
    envelope = TriggerEnvelope(
        trigger_type="user_message",
        user_id=str(actor.pk),
        operation_id=run.operation_id,
        conversation_id=run.conversation_id,
        payload={"message": run.input_message},
        triggered_at=current_time,
    )
    context = runtime_context_from_trigger(
        envelope,
        request_id=run.request_id,
        timezone=timezone_name,
        locale=locale,
        actor=actor,
        agent_run_id=str(run.pk),
    )

    try:
        with open_langgraph_persistence() as persistence:
            agent = build_time_steward_agent(model=model)
            runtime = build_outer_graph_runtime(
                OuterGraphNodes(
                    time_steward_agent=agent,
                    briefing_workflow=_unavailable_workflow,
                    calendar_sync_workflow=_unavailable_workflow,
                ),
                checkpointer=persistence.checkpointer,
                store=persistence.store,
            )
            result, emitted_delta = _consume_stream(runtime.stream(envelope, context), run)
        final_response = _last_ai_text(result)
        if not emitted_delta:
            AgentRunService.append_event(run, "message.delta", {"content": final_response})
        return AgentRunService.complete(run, final_response)
    except AgentRunCancelled:
        return AgentRun.objects.get(pk=run.pk)
    except Exception as exc:
        AgentRunService.fail(run, exc)
        raise


def _last_ai_text(state: AppState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, AIMessage):
            text = _message_text(message)
            if not text.strip():
                raise RuntimeError("Time Steward completed with an empty final AI message")
            return text
    raise RuntimeError("Time Steward completed without a final AI message")


def _message_text(message: AIMessage | AIMessageChunk) -> str:
    if isinstance(message.content, str):
        return message.content
    if isinstance(message.content, list):
        return "".join(
            str(block.get("text", ""))
            for block in message.content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def _consume_stream(stream: Any, run: AgentRun) -> tuple[AppState, bool]:
    latest: AppState | None = None
    emitted_delta = False
    for item in stream:
        if AgentRunService.is_cancelled(run.pk):
            raise AgentRunCancelled
        mode, data = _stream_mode_data(item)
        if mode == "values" and isinstance(data, dict):
            latest = cast(AppState, data)
        elif mode == "messages" and isinstance(data, tuple) and data:
            chunk = data[0]
            if isinstance(chunk, AIMessageChunk):
                text = _message_text(chunk)
                if not text:
                    continue
                AgentRunService.append_event(run, "message.delta", {"content": text})
                emitted_delta = True
        elif mode == "custom" and isinstance(data, dict):
            event_type = data.get("event_type")
            payload = data.get("payload", {})
            if isinstance(event_type, str) and isinstance(payload, dict):
                AgentRunService.append_event(run, event_type, payload)
    if latest is None:
        raise RuntimeError("Time Steward stream completed without a final state")
    return latest, emitted_delta


def _stream_mode_data(item: Any) -> tuple[str, Any]:
    if isinstance(item, tuple):
        if len(item) == 3 and isinstance(item[1], str):
            return item[1], item[2]
        if len(item) == 2 and isinstance(item[0], str):
            return item[0], item[1]
        if len(item) == 2 and isinstance(item[0], AIMessage):
            return "messages", item
        if len(item) == 2 and isinstance(item[0], tuple):
            data = item[1]
            if isinstance(data, tuple) and data and isinstance(data[0], AIMessage):
                return "messages", data
            if isinstance(data, dict) and "event_type" in data:
                return "custom", data
            return "values", data
    return "values", item
