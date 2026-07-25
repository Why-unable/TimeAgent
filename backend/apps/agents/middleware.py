from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from asgiref.sync import sync_to_async
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from langchain.agents.middleware import (
    AgentMiddleware,
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ModelRequest,
    ModelResponse,
    ModelRetryMiddleware,
    SummarizationMiddleware,
    ToolCallLimitMiddleware,
    ToolCallRequest,
    ToolErrorMiddleware,
    ToolRetryMiddleware,
    dynamic_prompt,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

from apps.action_proposals.risk_policy import hitl_interrupt_policy, policy_for_tool
from apps.action_proposals.services import ActionProposalService
from apps.agents.configuration import get_agent_config
from apps.agents.context import RuntimeContext
from apps.agents.state import AppState
from apps.agents.tools import READ_ONLY_TOOLS, WRITE_TOOLS
from apps.agents.tools.handoff_tools import HANDOFF_TOOLS
from apps.conversations.models import ToolCallStatus
from apps.conversations.services import AgentRunService, ToolAuditService
from common.time import to_user_timezone

PROMPT_PATH = Path(__file__).with_name("prompts") / "time_steward.md"
BASE_SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8").strip()
READ_ONLY_NAMES = frozenset(tool.name for tool in READ_ONLY_TOOLS)
WRITE_NAMES = frozenset(tool.name for tool in WRITE_TOOLS)
HANDOFF_NAMES = frozenset(tool.name for tool in HANDOFF_TOOLS)


@dynamic_prompt
def runtime_system_prompt(request: ModelRequest[RuntimeContext]) -> SystemMessage:
    context = request.runtime.context
    mode = "read-only" if context.read_only else "read/write; high-risk tools require approval"
    local_anchor = to_user_timezone(context.current_datetime, context.timezone)
    return SystemMessage(
        content=(
            f"{BASE_SYSTEM_PROMPT}\n\n"
            "Runtime: this run's fixed time anchor is "
            f"{local_anchor.isoformat()} ({context.timezone}), UTC "
            f"{context.current_datetime.isoformat()}. Interpret relative dates against this "
            f"anchor. User timezone={context.timezone}; locale={context.locale}; mode={mode}.\n\n"
            f"{context.planning_preferences.as_prompt_block()}"
        )
    )


class ToolPolicyMiddleware(AgentMiddleware[AppState, RuntimeContext, Any]):
    """Expose only tools authorized by trusted runtime context."""

    def _request(self, request: ModelRequest[RuntimeContext]) -> ModelRequest[RuntimeContext]:
        allowed = (
            READ_ONLY_NAMES
            if request.runtime.context.read_only
            else (READ_ONLY_NAMES | WRITE_NAMES)
        )
        tools: list[BaseTool | dict[str, Any]] = [
            tool for tool in request.tools if isinstance(tool, BaseTool) and tool.name in allowed
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


class ToolAuditMiddleware(AgentMiddleware[AppState, RuntimeContext, Any]):
    """Persist tool lifecycle events and replay completed tool calls idempotently."""

    @staticmethod
    def _details(request: ToolCallRequest) -> tuple[RuntimeContext, str] | None:
        context = request.runtime.context
        tool_call_id = str(request.tool_call.get("id", "")).strip()
        if request.tool_call.get("name") in HANDOFF_NAMES:
            return None
        if (
            not isinstance(context, RuntimeContext)
            or context.actor is None
            or context.agent_run_id is None
            or not tool_call_id
        ):
            return None
        return context, tool_call_id

    @staticmethod
    def _stored_message(request: ToolCallRequest, result: Any) -> ToolMessage:
        if isinstance(result, dict) and "content" in result:
            content = result["content"]
        else:
            content = result
        return ToolMessage(
            content=content,
            tool_call_id=str(request.tool_call["id"]),
            name=str(request.tool_call["name"]),
        )

    @staticmethod
    def _json_result(result: Any) -> Any:
        if hasattr(result, "model_dump"):
            return result.model_dump(mode="json")
        return result

    @staticmethod
    def _begin(
        request: ToolCallRequest,
        context: RuntimeContext,
        tool_call_id: str,
    ) -> tuple[Any, bool]:
        assert context.actor is not None
        ActionProposalService.bind_tool_call(
            run_id=context.agent_run_id or "",
            tool_call_id=tool_call_id,
            tool_name=str(request.tool_call["name"]),
            arguments=dict(request.tool_call.get("args", {})),
        )
        audit, created = ToolAuditService.begin(
            run_id=context.agent_run_id or "",
            user=context.actor,
            tool_call_id=tool_call_id,
            tool_name=str(request.tool_call["name"]),
            arguments=dict(request.tool_call.get("args", {})),
            risk_level=(
                "high"
                if policy_for_tool(str(request.tool_call["name"])) is not None
                else ("low" if request.tool_call["name"] in WRITE_NAMES else "read")
            ),
        )
        if created:
            if policy_for_tool(audit.tool_name) is not None:
                ActionProposalService.mark_executing(
                    run_id=context.agent_run_id or "",
                    tool_call_id=tool_call_id,
                )
            AgentRunService.append_event(
                audit.run,
                "tool.started",
                {"tool_call_id": tool_call_id, "tool_name": audit.tool_name},
            )
        return audit, created

    @staticmethod
    def _append_event(audit: Any, event_type: str, tool_call_id: str) -> None:
        AgentRunService.append_event(
            audit.run,
            event_type,
            {"tool_call_id": tool_call_id, "tool_name": audit.tool_name},
        )

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Any],
    ) -> ToolMessage | Any:
        details = self._details(request)
        if details is None:
            return handler(request)
        context, tool_call_id = details
        audit, created = self._begin(request, context, tool_call_id)
        if audit.status == ToolCallStatus.COMPLETED:
            return self._stored_message(request, audit.result)
        if audit.status == ToolCallStatus.FAILED:
            raise RuntimeError("A previous execution of this tool call failed")
        if not created:
            raise RuntimeError("This tool call is already running")
        try:
            with transaction.atomic():
                result = handler(request)
                ToolAuditService.complete(audit, self._json_result(result))
                ActionProposalService.mark_executed(
                    run_id=context.agent_run_id or "",
                    tool_call_id=tool_call_id,
                    result=self._json_result(result),
                )
                self._append_event(audit, "tool.completed", tool_call_id)
                return result
        except Exception as exc:
            ToolAuditService.fail(audit, exc)
            ActionProposalService.mark_failed(
                run_id=context.agent_run_id or "",
                tool_call_id=tool_call_id,
                error=exc,
            )
            self._append_event(audit, "tool.failed", tool_call_id)
            raise

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Any]],
    ) -> ToolMessage | Any:
        details = self._details(request)
        if details is None:
            return await handler(request)
        context, tool_call_id = details
        audit, created = await sync_to_async(self._begin)(request, context, tool_call_id)
        if audit.status == ToolCallStatus.COMPLETED:
            return self._stored_message(request, audit.result)
        if audit.status == ToolCallStatus.FAILED:
            raise RuntimeError("A previous execution of this tool call failed")
        if not created:
            raise RuntimeError("This tool call is already running")
        try:
            result = await handler(request)
            await sync_to_async(ToolAuditService.complete)(audit, self._json_result(result))
            await sync_to_async(ActionProposalService.mark_executed)(
                run_id=context.agent_run_id or "",
                tool_call_id=tool_call_id,
                result=self._json_result(result),
            )
            await sync_to_async(self._append_event)(
                audit,
                "tool.completed",
                tool_call_id,
            )
            return result
        except Exception as exc:
            await sync_to_async(ToolAuditService.fail)(audit, exc)
            await sync_to_async(ActionProposalService.mark_failed)(
                run_id=context.agent_run_id or "",
                tool_call_id=tool_call_id,
                error=exc,
            )
            await sync_to_async(self._append_event)(
                audit,
                "tool.failed",
                tool_call_id,
            )
            raise


def recoverable_tool_error(exc: Exception, request: ToolCallRequest) -> str | None:
    if isinstance(exc, (ValueError, PermissionError, ObjectDoesNotExist, ValidationError)):
        return f"Tool {request.tool_call['name']} could not complete: {type(exc).__name__}: {exc}"
    return None


def build_time_steward_middleware(
    model: BaseChatModel,
    *,
    fallback_models: list[BaseChatModel] | None = None,
) -> list[Any]:
    config = get_agent_config().middleware
    read_only_retry_tools: list[BaseTool | str] = list(READ_ONLY_TOOLS)
    middleware: list[Any] = [
        runtime_system_prompt,
        ToolPolicyMiddleware(),
        HumanInTheLoopMiddleware(interrupt_on=hitl_interrupt_policy()),
        ToolAuditMiddleware(),
        ModelCallLimitMiddleware(
            run_limit=config.model_call_limit,
            exit_behavior="end",
        ),
        ToolCallLimitMiddleware(
            run_limit=config.tool_call_limit,
            exit_behavior="continue",
        ),
    ]
    if fallback_models:
        middleware.append(ModelFallbackMiddleware(*fallback_models))
    middleware.extend(
        [
            ModelRetryMiddleware(
                max_retries=config.model_retry_limit,
                on_failure="error",
            ),
            ToolRetryMiddleware(
                max_retries=config.tool_retry_limit,
                tools=read_only_retry_tools,
                on_failure="error",
            ),
            ToolErrorMiddleware(recoverable_tool_error),
        ]
    )
    if config.summarization.enabled:
        middleware.append(
            SummarizationMiddleware(
                model,
                trigger=("messages", config.summarization.trigger_messages),
                keep=("messages", config.summarization.keep_messages),
            )
        )
    return middleware
