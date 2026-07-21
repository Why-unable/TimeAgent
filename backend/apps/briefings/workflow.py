from __future__ import annotations

from datetime import date
from typing import Any, Literal, cast
from uuid import UUID

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime

from apps.agents.context import RuntimeContext
from apps.agents.state import AppState
from apps.briefings.agent import (
    PROMPT_VERSION,
    BriefingAgentExecution,
    BriefingAgentRunner,
    briefing_model_snapshot,
    build_briefing_agent,
    research_section_results,
    run_briefing_agent,
)
from apps.briefings.rendering import render_markdown
from apps.briefings.schemas import (
    BriefingAgentRequest,
    BriefingResult,
    BriefingSectionKey,
    SectionResult,
)
from apps.briefings.services import BriefingRunService, StartBriefingCommand
from apps.conversations.models import AgentRun
from apps.preferences.services import UserPreferenceService
from common.time import get_timezone


def _emit(event_type: str, payload: dict[str, Any]) -> None:
    get_stream_writer()({"event_type": event_type, "payload": payload})


def briefing_workflow_node(
    state: AppState,
    runtime: Runtime[RuntimeContext],
    *,
    model: BaseChatModel | None = None,
    runner: BriefingAgentRunner | None = None,
) -> dict[str, Any]:
    """Run one ephemeral Briefing Agent and hand its audited result back to the conversation."""

    actor = runtime.context.actor
    if actor is None:
        raise PermissionError("Briefing workflow requires an authenticated actor")
    payload = state.get("trigger_payload", {})
    start_date = _payload_date(payload, "start_date") or _payload_date(payload, "target_date")
    if start_date is None:
        start_date = runtime.context.current_datetime.astimezone(
            get_timezone(runtime.context.timezone)
        ).date()
    end_date = _payload_date(payload, "end_date") or start_date
    if end_date < start_date:
        raise ValueError("Briefing end_date must not be earlier than start_date")
    raw_definition_id = payload.get("briefing_definition_id")
    definition_id = UUID(raw_definition_id) if isinstance(raw_definition_id, str) else None
    agent_run = (
        AgentRun.objects.get(pk=runtime.context.agent_run_id)
        if runtime.context.agent_run_id
        else None
    )
    run = BriefingRunService.start(
        StartBriefingCommand(
            user=actor,
            operation_id=UUID(state["operation_id"]),
            trigger_type=state.get("trigger_type", "manual_briefing"),
            target_date=start_date,
            timezone=runtime.context.timezone,
            definition_id=definition_id,
            conversation=agent_run.conversation if agent_run else None,
            agent_run=agent_run,
            requested_sections=(
                _requested_sections(payload, [])
                if _string_list(payload.get("requested_sections"))
                else None
            ),
        )
    )
    run = BriefingRunService.mark_running(run)
    _emit("briefing.run.started", {"briefing_run_id": str(run.pk)})
    definition = run.definition_snapshot
    requested_sections = cast(
        list[BriefingSectionKey],
        [
            str(item)
            for item in definition.get("requested_sections", definition["enabled_sections"])
        ],
    )
    for section_key in requested_sections:
        BriefingRunService.start_section(run, str(section_key))
        _emit("briefing.section.started", {"section": str(section_key)})

    preference = UserPreferenceService.get_for_user(actor)
    request = BriefingAgentRequest(
        objective=_objective(payload, state),
        start_date=start_date,
        end_date=end_date,
        requested_sections=requested_sections,
        locations=_string_list(payload.get("locations"))
        or ([preference.weather_location] if preference and preference.weather_location else []),
        news_topics=_string_list(payload.get("news_topics"))
        or (list(preference.news_topics) if preference else []),
        style=cast(Literal["concise", "balanced", "detailed"], definition.get("style", "balanced")),
        constraints=_string_list(payload.get("constraints")),
        previous_briefing_run_id=_optional_string(payload.get("previous_briefing_run_id")),
        previous_feedback=_optional_string(payload.get("previous_feedback")),
    )
    if runner is None:
        agent = build_briefing_agent(model=model) if model is not None else None

        def default_runner(
            request: BriefingAgentRequest,
            context: RuntimeContext,
        ) -> BriefingAgentExecution:
            return run_briefing_agent(request, context, agent=agent)

        execute_runner: BriefingAgentRunner = default_runner
    else:
        execute_runner = runner

    try:
        execution = execute_runner(request, runtime.context)
        section_results = research_section_results(execution.research_results)
        _persist_sections(run, requested_sections, section_results)
        sources = [source for item in section_results for source in item.sources]
        warnings = _deduplicate(
            [
                *(warning for item in section_results for warning in item.warnings),
                *execution.report.warnings,
                *execution.report.failed_attempts,
                *execution.report.unmet_requirements,
            ]
        )
        partial = bool(
            execution.used_fallback
            or execution.report.failed_attempts
            or execution.report.unmet_requirements
            or execution.report.coverage.missing_sections
            or any(item.status == "failed" for item in section_results)
        )
        status: Literal["completed", "partial"] = "partial" if partial else "completed"
        markdown = render_markdown(
            execution.report.draft,
            warnings=warnings,
            include_empty_sections=bool(definition.get("include_empty_sections", False)),
        )
        result = BriefingResult(
            run_id=str(run.pk),
            target_date=start_date,
            timezone=run.timezone,
            status=status,
            draft=execution.report.draft,
            markdown=markdown,
            sources=sources,
            warnings=warnings,
        )
        snapshot = briefing_model_snapshot() if model is None else {"model": type(model).__name__}
        BriefingRunService.complete(
            run,
            result,
            agent_report=execution.report,
            model_config_snapshot={str(key): str(value) for key, value in snapshot.items()},
            prompt_version=PROMPT_VERSION,
        )
    except Exception as exc:
        BriefingRunService.fail(run, code=type(exc).__name__, message=str(exc))
        raise

    messages: list[Any] = []
    tool_call_id = payload.get("briefing_tool_call_id")
    tool_message_id = payload.get("briefing_tool_message_id")
    artifact = {
        **result.model_dump(mode="json"),
        "research_report": execution.report.model_dump(mode="json"),
    }
    if isinstance(tool_call_id, str) and isinstance(tool_message_id, str):
        messages.append(
            ToolMessage(
                id=tool_message_id,
                content=(
                    f"简报生成完成，BriefingRun ID：{run.pk}；"
                    f"状态：{result.status}；调研警告：{len(result.warnings)} 项。"
                ),
                tool_call_id=tool_call_id,
                name="transfer_to_briefing",
                artifact=artifact,
            )
        )
        _emit("handoff.completed", {"source": "briefing_agent"})
    ai_message = AIMessage(
        id=f"briefing-{run.pk}",
        content=result.markdown,
        additional_kwargs={
            "briefing_run_id": str(run.pk),
            "briefing_status": result.status,
            "sources": [item.model_dump(mode="json") for item in result.sources],
            "warnings": result.warnings,
        },
    )
    messages.append(ai_message)
    for chunk in _markdown_chunks(result.markdown):
        _emit("message.delta", {"content": chunk, "message_id": ai_message.id})
    _emit("briefing.run.completed", {"briefing_run_id": str(run.pk), "status": result.status})
    return {
        "messages": messages,
        "active_workflow": "time_steward_agent",
        "workflow_result": {
            "workflow": "briefing_workflow",
            "briefing_run_id": str(run.pk),
            "status": result.status,
        },
    }


def _persist_sections(
    run: Any,
    requested_sections: list[BriefingSectionKey],
    results: list[SectionResult],
) -> None:
    by_key = {item.key: item for item in results}
    for section in requested_sections:
        result = by_key.get(section) or SectionResult(
            key=section,
            status="failed",
            warnings=[f"{section} 未产生可持久化的调研结果。"],
            error_code="ResearchResultMissing",
        )
        BriefingRunService.finish_section(run, result)
        _emit("briefing.section.completed", {"section": section, "status": result.status})


def _objective(payload: dict[str, Any], state: AppState) -> str:
    explicit = _optional_string(payload.get("request"))
    if explicit:
        return explicit
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage) and isinstance(message.content, str):
            if message.content.strip():
                return message.content.strip()
    return "根据我的偏好生成时间管理简报。"


def _requested_sections(payload: dict[str, Any], defaults: list[Any]) -> list[BriefingSectionKey]:
    raw = _string_list(payload.get("requested_sections")) or [str(item) for item in defaults]
    allowed = {"calendar", "tasks", "weather", "news"}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"Unknown briefing sections: {sorted(unknown)}")
    return cast(list[BriefingSectionKey], list(dict.fromkeys(raw)))


def _payload_date(payload: dict[str, Any], key: str) -> date | None:
    value = payload.get(key)
    return date.fromisoformat(value) if isinstance(value, str) and value.strip() else None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _optional_string(value: Any) -> str | None:
    normalized = str(value).strip() if value is not None else ""
    return normalized or None


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in values if item.strip()))


def _markdown_chunks(markdown: str, *, size: int = 96) -> list[str]:
    return [markdown[index : index + size] for index in range(0, len(markdown), size)]
