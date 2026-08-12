from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ModelRequest,
    ModelResponse,
    ModelRetryMiddleware,
    ToolCallLimitMiddleware,
    ToolCallRequest,
    ToolErrorMiddleware,
    ToolRetryMiddleware,
    dynamic_prompt,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.types import Command

from apps.agents.configuration import get_agent_config
from apps.agents.context import RuntimeContext
from apps.briefings.schemas import BriefingAgentRequest
from apps.briefings.state import BriefingAgentState
from apps.briefings.tools import BRIEFING_RESEARCH_TOOLS, EXTERNAL_RESEARCH_TOOLS
from apps.observability.llm_middleware import LLMUsageMiddleware
from common.prompt_security import UntrustedToolDataMiddleware

PROMPT_PATH = Path(__file__).with_name("prompts") / "briefing_agent.md"
BASE_SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8").strip()
RESEARCH_TOOL_NAMES = frozenset(tool.name for tool in BRIEFING_RESEARCH_TOOLS)
SECTION_TOOLS = {
    "calendar": {"research_calendar"},
    "tasks": {"research_tasks"},
    "weather": {"research_weather"},
    "news": {"research_news"},
}
PER_TOOL_RUN_LIMIT = 2


@dynamic_prompt
def briefing_runtime_prompt(request: ModelRequest[RuntimeContext]) -> SystemMessage:
    context = request.runtime.context
    return SystemMessage(
        content=(
            f"{BASE_SYSTEM_PROMPT}\n\n"
            f"可信运行时：当前 UTC 时间={context.current_datetime.isoformat()}；"
            f"用户时区={context.timezone}；语言区域={context.locale}。"
        )
    )


def _research_error(exc: Exception, request: ToolCallRequest) -> str | None:
    name = str(request.tool_call.get("name", "research tool"))
    if isinstance(
        exc,
        (
            httpx.HTTPError,
            TimeoutError,
            ConnectionError,
            LookupError,
            ValueError,
        ),
    ):
        return (
            f"{name} 在允许的重试次数用尽后仍然失败：{type(exc).__name__}: {exc}。"
            "请将此问题记录到 failed_attempts 和 unmet_requirements，"
            "然后继续收集其他证据，不要中止整份简报。"
        )
    return None


class BriefingToolPolicyMiddleware(AgentMiddleware[BriefingAgentState, RuntimeContext, Any]):
    """Expose only research tools required by the delegated request."""

    @staticmethod
    def _allowed(request: ModelRequest[RuntimeContext]) -> set[str]:
        if request.state.get("repair_mode", False):
            return set()
        delegated: BriefingAgentRequest | None = None
        for message in request.state.get("messages", []):
            content = getattr(message, "content", None)
            if not isinstance(content, str):
                continue
            try:
                delegated = BriefingAgentRequest.model_validate_json(content)
            except ValueError:
                continue
            break
        if delegated is None:
            return set(RESEARCH_TOOL_NAMES)

        raw_results = request.state.get("research_results", [])
        research_results = raw_results if isinstance(raw_results, list) else []
        settled_sections = {
            str(getattr(result, "section", ""))
            for result in research_results
            if str(getattr(result, "status", "")) in {"completed", "no_results"}
        }
        call_counts = _research_tool_call_counts(request.state.get("messages", []))
        # Expose one unfinished section at a time. Besides making the research
        # order deterministic, this keeps the provider's compiled tool grammar
        # small even when the request covers every briefing section.
        for section in delegated.requested_sections:
            if section in settled_sections:
                continue
            available = {
                name
                for name in SECTION_TOOLS[section]
                if call_counts.get(name, 0) < PER_TOOL_RUN_LIMIT
            }
            if available:
                return available
        return set()

    def _request(self, request: ModelRequest[RuntimeContext]) -> ModelRequest[RuntimeContext]:
        allowed = self._allowed(request)
        tools: list[BaseTool | dict[str, Any]] = [
            tool
            for tool in request.tools
            if not isinstance(tool, BaseTool)
            or tool.name not in RESEARCH_TOOL_NAMES
            or tool.name in allowed
        ]
        return request.override(tools=tools)

    def wrap_model_call(
        self,
        request: ModelRequest[RuntimeContext],
        handler: Callable[[ModelRequest[RuntimeContext]], ModelResponse],
    ) -> ModelResponse:
        return handler(self._request(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[RuntimeContext],
        handler: Callable[[ModelRequest[RuntimeContext]], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await handler(self._request(request))


class BriefingToolBudgetMiddleware(AgentMiddleware[BriefingAgentState, RuntimeContext, Any]):
    """Bound each research tool without leaving parallel tool calls unanswered."""

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        if request.state.get("repair_mode", False):
            return _repair_mode_tool_message(request)
        if _tool_call_ordinal(request) > PER_TOOL_RUN_LIMIT:
            return _tool_budget_message(request)
        return handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        if request.state.get("repair_mode", False):
            return _repair_mode_tool_message(request)
        if _tool_call_ordinal(request) > PER_TOOL_RUN_LIMIT:
            return _tool_budget_message(request)
        return await handler(request)


def _research_tool_call_counts(messages: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls:
            name = str(call.get("name", ""))
            if name in RESEARCH_TOOL_NAMES:
                counts[name] = counts.get(name, 0) + 1
    return counts


def _tool_call_ordinal(request: ToolCallRequest) -> int:
    target_id = str(request.tool_call.get("id", ""))
    target_name = str(request.tool_call.get("name", ""))
    ordinal = 0
    for message in request.state.get("messages", []):
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls:
            if str(call.get("name", "")) != target_name:
                continue
            ordinal += 1
            if str(call.get("id", "")) == target_id:
                return ordinal
    return ordinal


def _tool_budget_message(request: ToolCallRequest) -> ToolMessage:
    name = str(request.tool_call.get("name", "research_tool"))
    return ToolMessage(
        content=(
            f"{name} reached its per-run call limit. Do not call it again; "
            "complete the report with existing evidence and disclose any remaining gap."
        ),
        tool_call_id=str(request.tool_call.get("id", "")),
        name=name,
        status="error",
    )


def _repair_mode_tool_message(request: ToolCallRequest) -> ToolMessage:
    name = str(request.tool_call.get("name", "research_tool"))
    return ToolMessage(
        content=(
            "报告修复期间禁用研究工具。请使用已提供的证据提交结构化报告，"
            "并披露仍未解决的缺口。"
        ),
        tool_call_id=str(request.tool_call.get("id", "")),
        name=name,
        status="error",
    )


def build_briefing_middleware(
    *,
    fallback_models: list[BaseChatModel] | None = None,
) -> list[Any]:
    config = get_agent_config().middleware
    external_tools: list[BaseTool | str] = list(EXTERNAL_RESEARCH_TOOLS)
    middleware: list[Any] = [
        briefing_runtime_prompt,
        UntrustedToolDataMiddleware(),
        BriefingToolPolicyMiddleware(),
        BriefingToolBudgetMiddleware(),
        ModelCallLimitMiddleware(run_limit=config.model_call_limit, exit_behavior="end"),
        ToolCallLimitMiddleware(run_limit=config.tool_call_limit, exit_behavior="error"),
    ]
    if fallback_models:
        middleware.append(ModelFallbackMiddleware(*fallback_models))
    middleware.extend(
        [
            ModelRetryMiddleware(max_retries=config.model_retry_limit, on_failure="error"),
            # ToolError wraps ToolRetry: retry sees transient exceptions first;
            # only the exhausted error is converted into model-readable text.
            ToolErrorMiddleware(_research_error, tools=external_tools),
            ToolRetryMiddleware(
                max_retries=config.tool_retry_limit,
                tools=external_tools,
                retry_on=(httpx.TimeoutException, httpx.NetworkError, TimeoutError),
                on_failure="error",
                backoff_factor=2.0,
                initial_delay=0.5,
                max_delay=4.0,
                jitter=True,
            ),
        ]
    )
    middleware.append(LLMUsageMiddleware("briefing_agent"))
    return middleware
