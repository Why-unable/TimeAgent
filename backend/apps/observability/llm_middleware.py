import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

from asgiref.sync import sync_to_async
from django.db import DatabaseError
from langchain.agents.middleware import (
    AgentMiddleware,
    ExtendedModelResponse,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AIMessage, BaseMessage

from apps.agents.context import RuntimeContext
from apps.observability.services import LLMCallAuditService, RecordLLMCallCommand

logger = logging.getLogger(__name__)
MEMORY_BLOCK = re.compile(r"<time_behavior_memory>.*?</time_behavior_memory>", re.DOTALL)


def _model_name(request: ModelRequest[RuntimeContext]) -> str:
    for attribute in ("model_name", "model"):
        value = getattr(request.model, attribute, None)
        if isinstance(value, str) and value.strip():
            return value.strip()[:128]
    return type(request.model).__name__[:128]


def _response_messages(response: Any) -> list[BaseMessage]:
    if isinstance(response, ExtendedModelResponse):
        return list(response.model_response.result)
    if isinstance(response, ModelResponse):
        return list(response.result)
    if isinstance(response, AIMessage):
        return [response]
    return []


def _provider_usage(response: Any) -> tuple[int, int, int] | None:
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    found = False
    for message in _response_messages(response):
        if not isinstance(message, AIMessage):
            continue
        usage = message.usage_metadata
        if usage:
            input_tokens += int(usage.get("input_tokens") or 0)
            output_tokens += int(usage.get("output_tokens") or 0)
            total_tokens += int(usage.get("total_tokens") or 0)
            found = True
            continue
        raw_usage = message.response_metadata.get("token_usage") or message.response_metadata.get(
            "usage"
        )
        if isinstance(raw_usage, dict):
            raw_input = raw_usage.get("prompt_tokens", raw_usage.get("input_tokens", 0))
            raw_output = raw_usage.get("completion_tokens", raw_usage.get("output_tokens", 0))
            input_tokens += int(raw_input) if isinstance(raw_input, int | float | str) else 0
            output_tokens += int(raw_output) if isinstance(raw_output, int | float | str) else 0
            total_tokens += int(raw_usage.get("total_tokens", 0))
            found = True
    if not found:
        return None
    return input_tokens, output_tokens, total_tokens or input_tokens + output_tokens


def _memory_prompt(request: ModelRequest[RuntimeContext]) -> str:
    if request.system_message is None:
        return ""
    match = MEMORY_BLOCK.search(request.system_message.text)
    return match.group(0) if match else ""


def _count_text_tokens(request: ModelRequest[RuntimeContext], text: str) -> int:
    if not text:
        return 0
    try:
        return max(0, int(request.model.get_num_tokens(text)))
    except (ImportError, NotImplementedError, TypeError, ValueError):
        return max(1, round(len(text) / 1.5))


def _estimated_usage(
    request: ModelRequest[RuntimeContext], response: Any
) -> tuple[int, int, int] | None:
    messages: list[BaseMessage] = list(request.messages)
    if request.system_message is not None:
        messages.insert(0, request.system_message)
    try:
        input_tokens = int(
            request.model.get_num_tokens_from_messages(messages, tools=request.tools)
        )
        output_tokens = sum(
            _count_text_tokens(request, message.text)
            for message in _response_messages(response)
            if isinstance(message, AIMessage)
        )
    except (ImportError, NotImplementedError, TypeError, ValueError):
        return None
    return input_tokens, output_tokens, input_tokens + output_tokens


class LLMUsageMiddleware(AgentMiddleware[Any, RuntimeContext, Any]):
    def __init__(self, component: str, *, track_memory: bool = False) -> None:
        self.component = component
        self.track_memory = track_memory

    def _command(
        self,
        request: ModelRequest[RuntimeContext],
        *,
        response: Any,
        status: str,
        started_at: float,
        error: Exception | None = None,
    ) -> RecordLLMCallCommand:
        provider_usage = _provider_usage(response)
        usage = provider_usage or _estimated_usage(request, response)
        usage_source = "provider" if provider_usage else ("estimated" if usage else "unavailable")
        input_tokens, output_tokens, total_tokens = usage or (None, None, None)
        memory_tokens = (
            _count_text_tokens(request, _memory_prompt(request)) if self.track_memory else 0
        )
        memory_ratio = (
            min(1.0, memory_tokens / input_tokens)
            if memory_tokens and input_tokens and input_tokens > 0
            else (0.0 if input_tokens is not None else None)
        )
        context = request.runtime.context
        return RecordLLMCallCommand(
            request_id=getattr(context, "request_id", "-"),
            agent_run_id=getattr(context, "agent_run_id", "") or "",
            component=self.component,
            model_name=_model_name(request),
            status=status,
            usage_source=usage_source,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            memory_prompt_tokens=memory_tokens,
            memory_prompt_ratio=memory_ratio,
            duration_ms=max(0, round((time.monotonic() - started_at) * 1000)),
            error_type=type(error).__name__ if error is not None else "",
        )

    @staticmethod
    def _log(command: RecordLLMCallCommand) -> None:
        logger.info(
            "llm_call_completed" if command.status == "completed" else "llm_call_failed",
            extra={
                "request_id": command.request_id,
                "agent_run_id": command.agent_run_id,
                "component": command.component,
                "model": command.model_name,
                "llm_status": command.status,
                "usage_source": command.usage_source,
                "input_tokens": command.input_tokens,
                "output_tokens": command.output_tokens,
                "total_tokens": command.total_tokens,
                "memory_prompt_tokens": command.memory_prompt_tokens,
                "memory_prompt_ratio": command.memory_prompt_ratio,
                "duration_ms": command.duration_ms,
                "error_type": command.error_type,
            },
        )

    @classmethod
    def _record(cls, command: RecordLLMCallCommand) -> None:
        try:
            LLMCallAuditService.record(command)
        except (DatabaseError, ValueError):
            logger.warning(
                "llm_call_audit_failed",
                extra={
                    "request_id": command.request_id,
                    "agent_run_id": command.agent_run_id,
                    "component": command.component,
                    "model": command.model_name,
                    "llm_status": command.status,
                },
            )
        cls._log(command)

    def wrap_model_call(
        self,
        request: ModelRequest[RuntimeContext],
        handler: Callable[[ModelRequest[RuntimeContext]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        started_at = time.monotonic()
        try:
            response = handler(request)
        except Exception as exc:
            self._record(
                self._command(
                    request,
                    response=None,
                    status="failed",
                    started_at=started_at,
                    error=exc,
                )
            )
            raise
        self._record(
            self._command(
                request,
                response=response,
                status="completed",
                started_at=started_at,
            )
        )
        return response

    async def awrap_model_call(
        self,
        request: ModelRequest[RuntimeContext],
        handler: Callable[[ModelRequest[RuntimeContext]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        started_at = time.monotonic()
        try:
            response = await handler(request)
        except Exception as exc:
            command = self._command(
                request,
                response=None,
                status="failed",
                started_at=started_at,
                error=exc,
            )
            await sync_to_async(self._record, thread_sensitive=True)(command)
            raise
        command = self._command(
            request,
            response=response,
            status="completed",
            started_at=started_at,
        )
        await sync_to_async(self._record, thread_sensitive=True)(command)
        return response
