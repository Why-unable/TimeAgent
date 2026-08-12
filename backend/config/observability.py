"""Small, dependency-free request correlation helpers for production logs."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from contextvars import ContextVar
from uuid import uuid4

from django.http import HttpRequest, HttpResponse

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")
logger = logging.getLogger("time_agent.request")


class SafeJsonFormatter(logging.Formatter):
    """Serialize an allowlisted log record without exception messages or tracebacks."""

    extra_fields = (
        "request_id",
        "method",
        "path",
        "status_code",
        "duration_ms",
        "agent_run_id",
        "error_code",
        "tool_name",
        "provider",
        "error_type",
        "component",
        "model",
        "llm_status",
        "usage_source",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "memory_prompt_tokens",
        "memory_prompt_ratio",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "source": f"{record.module}:{record.funcName}:{record.lineno}",
        }
        for field in self.extra_fields:
            value = getattr(record, field, None)
            if value not in (None, "-"):
                payload[field] = value
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False, default=str)


def current_request_id() -> str:
    """Return the correlation identifier for the current HTTP request."""

    return request_id_context.get()


class RequestContextMiddleware:
    """Attach a safe request id to responses and structured application logs."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        supplied_id = request.headers.get("X-Request-ID", "").strip()
        request_id = supplied_id[:128] if supplied_id.isascii() and supplied_id else str(uuid4())
        token = request_id_context.set(request_id)
        started_at = time.monotonic()
        try:
            response = self.get_response(request)
        finally:
            elapsed_ms = round((time.monotonic() - started_at) * 1000, 2)
            request_id_context.reset(token)

        response["X-Request-ID"] = request_id
        logger.info(
            "http_request_complete",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": elapsed_ms,
            },
        )
        return response
