from datetime import date
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from apps.agents.context import RuntimeContext
from apps.conversations.services import AgentRunService


@tool
def transfer_to_briefing(
    request: str,
    target_date: date | None,
    runtime: ToolRuntime[RuntimeContext, dict[str, Any]],
) -> Command[Any]:
    """Transfer a daily briefing request to the deterministic Briefing Workflow.

    Use this only when the user explicitly asks to generate or prepare a briefing. Pass the user's
    request without embellishment and an ISO target date when it is explicit.
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
    if target_date is not None:
        payload["target_date"] = target_date.isoformat()
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
