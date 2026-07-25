"""Small, dependency-free request correlation helpers for production logs."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextvars import ContextVar
from uuid import uuid4

from django.http import HttpRequest, HttpResponse

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")
logger = logging.getLogger("time_agent.request")


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
