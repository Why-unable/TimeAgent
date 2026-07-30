from datetime import date
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from apps.agents.context import RuntimeContext
from apps.briefings.schemas import BriefingSectionKey
from apps.conversations.services import AgentRunService


@tool
def transfer_to_briefing(
    request: str,
    runtime: ToolRuntime[RuntimeContext, dict[str, Any]],
    start_date: date | None = None,
    end_date: date | None = None,
    target_date: date | None = None,
    requested_sections: list[BriefingSectionKey] | None = None,
    locations: list[str] | None = None,
    news_topics: list[str] | None = None,
    constraints: list[str] | None = None,
    previous_briefing_run_id: str | None = None,
    previous_feedback: str | None = None,
) -> Command[Any]:
    """Delegate a briefing request to the specialized, read-only Briefing Agent.

    ``requested_sections`` is a closed machine contract: use only calendar, tasks, weather, or
    news. Keep the complete natural-language request (for example, "latest domestic news") in
    ``request`` and put its filters in ``locations``, ``news_topics``, or ``constraints``.
    Preserve the user's requested date range and explicit feedback. target_date is a legacy alias.
    """

    tool_call_id = (runtime.tool_call_id or "").strip()
    if not tool_call_id:
        raise RuntimeError("Briefing handoff requires a tool call ID")
    last_ai_message = next(
        (
            message
            for message in reversed(runtime.state.get("messages", []))
            if isinstance(message, AIMessage)
        ),
        None,
    )
    if last_ai_message is None:
        raise RuntimeError("Briefing handoff requires the initiating AI message")
    transfer_message = ToolMessage(
        id=f"briefing-transfer-{tool_call_id}",
        content="简报工作流已接管请求，正在收集数据。",
        tool_call_id=tool_call_id,
        name="transfer_to_briefing",
    )
    if runtime.context.agent_run_id:
        from apps.conversations.models import AgentRun

        run = AgentRun.objects.get(pk=runtime.context.agent_run_id)
        AgentRunService.append_event(
            run,
            "handoff.started",
            {"destination": "briefing_workflow", "tool_call_id": tool_call_id},
        )
    payload: dict[str, Any] = {
        "request": request.strip(),
        "briefing_tool_call_id": tool_call_id,
        "briefing_tool_message_id": transfer_message.id,
    }
    effective_start = start_date or target_date
    if effective_start is not None:
        payload["start_date"] = effective_start.isoformat()
        payload["target_date"] = effective_start.isoformat()
    if end_date is not None:
        payload["end_date"] = end_date.isoformat()
    for key, value in (
        ("requested_sections", requested_sections),
        ("locations", locations),
        ("news_topics", news_topics),
        ("constraints", constraints),
    ):
        if value:
            payload[key] = [item.strip() for item in value if item.strip()]
    if previous_briefing_run_id and previous_briefing_run_id.strip():
        payload["previous_briefing_run_id"] = previous_briefing_run_id.strip()
    if previous_feedback and previous_feedback.strip():
        payload["previous_feedback"] = previous_feedback.strip()
    return Command(
        goto="briefing_workflow",
        update={
            "active_workflow": "briefing_workflow",
            "trigger_payload": payload,
            "messages": [last_ai_message, transfer_message],
        },
        graph=Command.PARENT,
    )


HANDOFF_TOOLS = [transfer_to_briefing]
