from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy, ToolStrategy
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import Runnable
from langchain_core.utils.json import parse_json_markdown

from apps.agents.configuration import get_agent_config
from apps.agents.context import RuntimeContext
from apps.agents.model import build_chat_model, build_fallback_chat_models
from apps.briefings.middleware import build_briefing_middleware
from apps.briefings.rendering import fallback_draft, validate_draft
from apps.briefings.schemas import (
    BriefingAgentReport,
    BriefingAgentRequest,
    BriefingCoverage,
    ResearchSummary,
    ResearchToolResult,
    SectionResult,
)
from apps.briefings.state import BriefingAgentState
from apps.briefings.tools import BRIEFING_RESEARCH_TOOLS

PROMPT_VERSION = "briefing-agent-v1-research-tools"
TOOL_SECTION = {
    "research_calendar": "calendar",
    "research_tasks": "tasks",
    "research_weather": "weather",
    "research_news": "news",
}


@dataclass(frozen=True, slots=True)
class BriefingAgentExecution:
    report: BriefingAgentReport
    research_results: list[ResearchToolResult]
    messages: list[BaseMessage]
    validation_errors: list[str] = field(default_factory=list)
    used_fallback: bool = False


class BriefingAgentRunner(Protocol):
    def __call__(
        self,
        request: BriefingAgentRequest,
        context: RuntimeContext,
    ) -> BriefingAgentExecution: ...


def build_briefing_agent(
    *,
    model: BaseChatModel | None = None,
    model_alias: str | None = None,
) -> Runnable[Any, Any]:
    config = get_agent_config()
    alias = model_alias or config.agent.selected_briefing_model
    resolved_model = model or build_chat_model(alias)
    fallback_models = [] if model is not None else build_fallback_chat_models()
    strategy = (
        config.selected_model(alias).structured_output_strategy
        if model_alias or model is None
        else "auto"
    )
    response_format: Any
    if strategy == "tool":
        response_format = ToolStrategy(BriefingAgentReport)
    elif strategy == "provider":
        response_format = ProviderStrategy(BriefingAgentReport)
    else:
        response_format = BriefingAgentReport
    return create_agent(
        model=resolved_model,
        tools=BRIEFING_RESEARCH_TOOLS,
        middleware=build_briefing_middleware(fallback_models=fallback_models),
        response_format=response_format,
        state_schema=BriefingAgentState,
        context_schema=RuntimeContext,
        name="briefing_agent",
    )


def run_briefing_agent(
    request: BriefingAgentRequest,
    context: RuntimeContext,
    *,
    agent: Runnable[Any, Any] | None = None,
    max_repairs: int = 1,
) -> BriefingAgentExecution:
    resolved_agent = agent or build_briefing_agent()
    request_message = HumanMessage(
        content=json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
    )
    state: dict[str, Any] = {"messages": [request_message], "research_results": []}
    result = _invoke(resolved_agent, state, context)
    errors = _validate_execution(request, result)
    repairs = 0
    while errors and repairs < max_repairs:
        repairs += 1
        research = _research_results(result)
        repair_message = HumanMessage(
            content=json.dumps(
                {
                    "instruction": (
                        "Return a corrected BriefingAgentReport using only the supplied research "
                        "evidence. Do not call tools and do not invent sources."
                    ),
                    "validation_errors": errors,
                    "research_evidence": [item.model_dump(mode="json") for item in research],
                },
                ensure_ascii=False,
            )
        )
        state = {
            # A repair is a fresh formatting pass. Replaying a completed agent's
            # internal tool-call transcript as a new invocation can violate provider
            # message-pairing rules and unnecessarily re-expose research tools.
            "messages": [request_message, repair_message],
            "research_results": research,
            "attempted_sections": sorted(_attempted_sections(result)),
            "repair_mode": True,
        }
        result = _invoke(resolved_agent, state, context)
        errors = _validate_execution(request, result)
    if errors:
        return _fallback_execution(request, result, errors)
    report = _extract_report(result)
    assert report is not None
    return BriefingAgentExecution(
        report=report,
        research_results=_research_results(result),
        messages=list(result.get("messages", [])),
        validation_errors=[],
    )


def _invoke(
    agent: Runnable[Any, Any],
    state: dict[str, Any],
    context: RuntimeContext,
) -> dict[str, Any]:
    result = agent.invoke(state, context=context)
    if not isinstance(result, dict):
        raise RuntimeError("Briefing Agent returned an invalid state")
    return cast(dict[str, Any], result)


def _validate_execution(request: BriefingAgentRequest, result: dict[str, Any]) -> list[str]:
    report = _extract_report(result)
    if report is None:
        detail = _report_parse_error(result)
        message = "Briefing Agent did not return valid BriefingAgentReport structured output"
        return [f"{message}: {detail}" if detail else message]
    attempted = _attempted_sections(result)
    errors = [
        f"requested section was not researched: {section}"
        for section in request.requested_sections
        if section not in attempted
    ]
    summaries = {item.section for item in report.research_summary}
    errors.extend(
        f"research_summary is missing requested section: {section}"
        for section in request.requested_sections
        if section not in summaries
    )
    if report.coverage.start_date != request.start_date:
        errors.append("coverage.start_date does not match the delegated request")
    if report.coverage.end_date != request.end_date:
        errors.append("coverage.end_date does not match the delegated request")
    try:
        validate_draft(report.draft, research_section_results(_research_results(result)))
    except ValueError as exc:
        errors.append(str(exc))
    return errors


def _attempted_sections(result: dict[str, Any]) -> set[str]:
    attempted = {
        item.section for item in _research_results(result) if item.section in TOOL_SECTION.values()
    }
    attempted.update(str(item) for item in result.get("attempted_sections", []))
    attempted.update(
        TOOL_SECTION[str(call.get("name"))]
        for message in result.get("messages", [])
        if isinstance(message, AIMessage)
        for call in message.tool_calls
        if str(call.get("name")) in TOOL_SECTION
    )
    return attempted


def _research_results(result: dict[str, Any]) -> list[ResearchToolResult]:
    return [
        item if isinstance(item, ResearchToolResult) else ResearchToolResult.model_validate(item)
        for item in result.get("research_results", [])
    ]


def _extract_report(result: dict[str, Any]) -> BriefingAgentReport | None:
    structured = result.get("structured_response")
    if structured is not None:
        try:
            return BriefingAgentReport.model_validate(structured)
        except ValueError:
            pass
    for message in reversed(result.get("messages", [])):
        if not isinstance(message, AIMessage):
            continue
        repaired = _report_from_invalid_tool_call(message)
        if repaired is not None:
            return repaired
        content = message.text.strip()
        if not content:
            continue
        try:
            return BriefingAgentReport.model_validate(parse_json_markdown(content))
        except ValueError:
            continue
    return None


def _report_from_invalid_tool_call(message: AIMessage) -> BriefingAgentReport | None:
    """Repair relay-malformed report arguments, then validate them strictly."""

    for call in message.invalid_tool_calls:
        if call.get("name") != BriefingAgentReport.__name__:
            continue
        raw_args = call.get("args")
        if not isinstance(raw_args, str) or not raw_args.strip():
            continue
        try:
            repaired_args = _escape_unquoted_string_quotes(raw_args)
            return BriefingAgentReport.model_validate(json.loads(repaired_args))
        except (TypeError, ValueError):
            continue
    return None


def _escape_unquoted_string_quotes(value: str) -> str:
    """Escape only quotes that cannot terminate the current JSON string."""

    output: list[str] = []
    in_string = False
    escaped = False
    for index, character in enumerate(value):
        if not in_string:
            output.append(character)
            if character == '"':
                in_string = True
            continue
        if escaped:
            output.append(character)
            escaped = False
            continue
        if character == "\\":
            output.append(character)
            escaped = True
            continue
        if character != '"':
            output.append(character)
            continue

        next_index = index + 1
        while next_index < len(value) and value[next_index].isspace():
            next_index += 1
        next_character = value[next_index] if next_index < len(value) else ""
        if not next_character or next_character in ",:}]":
            output.append(character)
            in_string = False
        else:
            output.append('\\"')
    return "".join(output)


def _report_parse_error(result: dict[str, Any]) -> str:
    for message in reversed(result.get("messages", [])):
        if not isinstance(message, AIMessage):
            continue
        content = message.text.strip()
        if not content:
            continue
        try:
            BriefingAgentReport.model_validate(parse_json_markdown(content))
        except ValueError as exc:
            # Feed a concise parser diagnostic into the bounded repair turn without
            # echoing the full generated report into state, logs, or user warnings.
            return "JSON parse/validation error: " + " ".join(str(exc).split())[:560]
    return ""


def research_section_results(results: list[ResearchToolResult]) -> list[SectionResult]:
    grouped: dict[str, list[ResearchToolResult]] = {}
    for item in results:
        if item.section in {"calendar", "tasks", "weather", "news"}:
            grouped.setdefault(item.section, []).append(item)
    sections: list[SectionResult] = []
    for key, items in grouped.items():
        sources = {source.id: source for item in items for source in item.sources}
        warnings = [warning for item in items for warning in item.warnings]
        # The most recent call is the agent's final refinement for that section.
        latest = items[-1]
        sections.append(
            SectionResult(
                key=key,
                status="failed" if all(item.status == "failed" for item in items) else "completed",
                data=latest.data,
                sources=list(sources.values()),
                warnings=warnings,
                error_code=latest.error_code,
            )
        )
    return sections


def _fallback_execution(
    request: BriefingAgentRequest,
    result: dict[str, Any],
    errors: list[str],
) -> BriefingAgentExecution:
    research = _research_results(result)
    sections = research_section_results(research)
    draft = fallback_draft(target_date=request.start_date.isoformat(), sections=sections)
    summaries = [
        ResearchSummary(
            section=section,
            status=(
                "failed"
                if not any(item.section == section for item in research)
                else next(item.status for item in reversed(research) if item.section == section)
            ),
            summary="Deterministic fallback used after Briefing Agent validation failed.",
            source_ids=[
                source.id for item in research if item.section == section for source in item.sources
            ],
            warnings=[
                warning for item in research if item.section == section for warning in item.warnings
            ],
        )
        for section in request.requested_sections
    ]
    report = BriefingAgentReport(
        draft=draft,
        research_summary=summaries,
        failed_attempts=errors,
        unmet_requirements=errors,
        warnings=["Briefing Agent output failed validation; deterministic fallback was used."],
        coverage=BriefingCoverage(
            start_date=request.start_date,
            end_date=request.end_date,
            covered_sections=sorted({item.section for item in research}),
            missing_sections=[
                section
                for section in request.requested_sections
                if not any(item.section == section for item in research)
            ],
        ),
    )
    return BriefingAgentExecution(
        report=report,
        research_results=research,
        messages=list(result.get("messages", [])),
        validation_errors=errors,
        used_fallback=True,
    )


def briefing_model_snapshot() -> dict[str, Any]:
    config = get_agent_config()
    alias = config.agent.selected_briefing_model
    definition = config.selected_model(alias)
    return {
        "alias": alias,
        "provider": definition.provider,
        "model": definition.model,
        "response_format": "BriefingAgentReport",
        "structured_output_strategy": definition.structured_output_strategy,
    }
