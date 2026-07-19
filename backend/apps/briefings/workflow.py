import operator
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any, Literal, TypedDict, cast
from uuid import UUID

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import Runnable
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from apps.agents.context import RuntimeContext
from apps.agents.state import AppState
from apps.briefings.editor import PROMPT_VERSION, edit_briefing, editor_model_snapshot
from apps.briefings.registry import BriefingRegistry, SectionContext
from apps.briefings.rendering import fallback_draft, render_markdown, validate_draft
from apps.briefings.schemas import BriefingResult, SectionResult, SourceReference
from apps.briefings.sections import DEFAULT_BRIEFING_REGISTRY
from apps.briefings.services import BriefingRunService, StartBriefingCommand
from apps.conversations.models import AgentRun
from common.time import get_timezone


class BriefingState(TypedDict):
    run_id: str
    section_keys: list[str]
    target_date: str
    timezone: str
    locale: str
    style: str
    include_empty_sections: bool
    request_text: str
    section_results: Annotated[list[SectionResult], operator.add]
    draft: dict[str, Any]
    warnings: list[str]
    markdown: str
    used_fallback: bool


def _emit(event_type: str, payload: dict[str, Any]) -> None:
    get_stream_writer()({"event_type": event_type, "payload": payload})


def _section_context(state: BriefingState, runtime: Runtime[RuntimeContext]) -> SectionContext:
    target = date.fromisoformat(state["target_date"])
    zone = get_timezone(state["timezone"])
    day_start = datetime.combine(target, time.min, tzinfo=zone).astimezone(UTC)
    day_end = datetime.combine(target + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    return SectionContext(
        target_date=target,
        timezone=state["timezone"],
        locale=state["locale"],
        current_datetime=runtime.context.current_datetime,
        day_start_at=day_start,
        day_end_at=day_end,
    )


def build_briefing_graph(
    *,
    registry: BriefingRegistry = DEFAULT_BRIEFING_REGISTRY,
    section_keys: list[str] | None = None,
    editor: Runnable[Any, Any] | None = None,
) -> Runnable[Any, Any]:
    builder = StateGraph(BriefingState, context_schema=RuntimeContext)
    selected_keys = section_keys or sorted(registry.keys)
    if not selected_keys:
        raise ValueError("Briefing workflow requires at least one section")
    unknown = set(selected_keys) - registry.keys
    if unknown:
        raise ValueError(f"Unknown briefing sections: {sorted(unknown)}")

    def collect(section_key: str) -> Any:
        def node(
            state: BriefingState, runtime: Runtime[RuntimeContext]
        ) -> dict[str, list[SectionResult]]:
            actor = runtime.context.actor
            if actor is None:
                raise PermissionError("Briefing collection requires an authenticated actor")
            try:
                result = registry.get(section_key).collect(
                    user=actor,
                    context=_section_context(state, runtime),
                )
            except Exception as exc:
                result = SectionResult(
                    key=section_key,
                    status="failed",
                    warnings=[f"{section_key} 数据暂时不可用。"],
                    error_code=type(exc).__name__,
                )
            _emit(
                "briefing.section.completed",
                {"section": section_key, "status": result.status},
            )
            return {"section_results": [result]}

        return node

    def normalize(state: BriefingState) -> dict[str, Any]:
        from apps.briefings.models import BriefingRun

        ordered = sorted(state["section_results"], key=lambda item: item.key)
        run = BriefingRun.objects.get(pk=state["run_id"])
        for result in ordered:
            BriefingRunService.finish_section(run, result)
        successful = [item for item in ordered if item.status == "completed"]
        if not successful:
            raise RuntimeError("All briefing sections failed")
        warnings = [warning for item in ordered for warning in item.warnings]
        return {"section_results": ordered, "warnings": warnings}

    def edit(state: BriefingState) -> dict[str, Any]:
        _emit("briefing.editor.started", {})
        used_fallback = False
        try:
            draft = edit_briefing(
                sections=state["section_results"],
                target_date=state["target_date"],
                timezone=state["timezone"],
                locale=state["locale"],
                style=state["style"],
                request_text=state["request_text"],
                editor=editor,
            )
            validate_draft(draft, state["section_results"])
        except Exception:
            draft = fallback_draft(
                target_date=state["target_date"], sections=state["section_results"]
            )
            used_fallback = True
        _emit("briefing.editor.completed", {"fallback": used_fallback})
        return {"draft": draft.model_dump(mode="json"), "used_fallback": used_fallback}

    def render(state: BriefingState) -> dict[str, str]:
        from apps.briefings.schemas import BriefingDraft

        draft = BriefingDraft.model_validate(state["draft"])
        return {
            "markdown": render_markdown(
                draft,
                warnings=state["warnings"],
                include_empty_sections=state["include_empty_sections"],
            )
        }

    for key in selected_keys:
        builder.add_node(f"collect_{key}", collect(key))
        builder.add_edge(START, f"collect_{key}")
    builder.add_node("normalize", normalize)
    builder.add_node("edit", edit)
    builder.add_node("render", render)
    builder.add_edge([f"collect_{key}" for key in selected_keys], "normalize")
    builder.add_edge("normalize", "edit")
    builder.add_edge("edit", "render")
    builder.add_edge("render", END)
    return builder.compile(name="briefing_workflow")


def briefing_workflow_node(
    state: AppState,
    runtime: Runtime[RuntimeContext],
    *,
    model: BaseChatModel | None = None,
    editor: Runnable[Any, Any] | None = None,
    registry: BriefingRegistry = DEFAULT_BRIEFING_REGISTRY,
) -> dict[str, Any]:
    actor = runtime.context.actor
    if actor is None:
        raise PermissionError("Briefing workflow requires an authenticated actor")
    payload = state.get("trigger_payload", {})
    raw_target_date = payload.get("target_date")
    if isinstance(raw_target_date, str):
        target_date = date.fromisoformat(raw_target_date)
    else:
        target_date = runtime.context.current_datetime.astimezone(
            get_timezone(runtime.context.timezone)
        ).date()
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
            target_date=target_date,
            timezone=runtime.context.timezone,
            definition_id=definition_id,
            conversation=agent_run.conversation if agent_run else None,
            agent_run=agent_run,
        )
    )
    run = BriefingRunService.mark_running(run)
    _emit("briefing.run.started", {"briefing_run_id": str(run.pk)})
    definition = run.definition_snapshot
    for section_key in definition["enabled_sections"]:
        BriefingRunService.start_section(run, str(section_key))
        _emit("briefing.section.started", {"section": str(section_key)})
    editor_agent = editor
    if editor_agent is None and model is not None:
        from apps.briefings.editor import build_briefing_editor_agent

        editor_agent = build_briefing_editor_agent(model=model)
    graph = build_briefing_graph(
        registry=registry,
        section_keys=list(definition["enabled_sections"]),
        editor=editor_agent,
    )
    try:
        output = cast(
            BriefingState,
            graph.invoke(
                {
                    "run_id": str(run.pk),
                    "section_keys": list(definition["enabled_sections"]),
                    "target_date": target_date.isoformat(),
                    "timezone": run.timezone,
                    "locale": str(definition.get("locale") or runtime.context.locale),
                    "style": str(definition.get("style", "balanced")),
                    "include_empty_sections": bool(definition.get("include_empty_sections", False)),
                    "request_text": str(payload.get("request", "")),
                    "section_results": [],
                    "draft": {},
                    "warnings": [],
                    "markdown": "",
                    "used_fallback": False,
                },
                context=runtime.context,
            ),
        )
        from apps.briefings.schemas import BriefingDraft

        sections = output["section_results"]
        sources: list[SourceReference] = [source for item in sections for source in item.sources]
        status: Literal["completed", "partial"] = (
            "partial" if any(item.status == "failed" for item in sections) else "completed"
        )
        result = BriefingResult(
            run_id=str(run.pk),
            target_date=target_date,
            timezone=run.timezone,
            status=status,
            draft=BriefingDraft.model_validate(output["draft"]),
            markdown=output["markdown"],
            sources=sources,
            warnings=output["warnings"],
        )
        snapshot = editor_model_snapshot() if model is None else {"model": type(model).__name__}
        BriefingRunService.complete(
            run,
            result,
            model_config_snapshot={str(key): str(value) for key, value in snapshot.items()},
            prompt_version=PROMPT_VERSION,
        )
    except Exception as exc:
        BriefingRunService.fail(run, code=type(exc).__name__, message=str(exc))
        raise

    messages: list[Any] = []
    tool_call_id = payload.get("briefing_tool_call_id")
    tool_message_id = payload.get("briefing_tool_message_id")
    if isinstance(tool_call_id, str) and isinstance(tool_message_id, str):
        messages.append(
            ToolMessage(
                id=tool_message_id,
                content=f"简报生成完成，BriefingRun ID：{run.pk}",
                tool_call_id=tool_call_id,
                name="transfer_to_briefing",
                artifact=result.model_dump(mode="json"),
            )
        )
        _emit("handoff.completed", {"source": "briefing_workflow"})
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


def _markdown_chunks(markdown: str, *, size: int = 96) -> list[str]:
    return [markdown[index : index + size] for index in range(0, len(markdown), size)]
