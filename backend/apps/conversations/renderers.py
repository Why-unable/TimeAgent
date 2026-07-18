from collections.abc import Mapping
from typing import Any

from rest_framework.renderers import BaseRenderer


class EventStreamRenderer(BaseRenderer):
    """Allow DRF content negotiation for a StreamingHttpResponse SSE body."""

    media_type = "text/event-stream"
    format = "sse"
    charset = None

    def render(
        self,
        data: Any,
        accepted_media_type: str | None = None,
        renderer_context: Mapping[str, Any] | None = None,
    ) -> bytes:
        del accepted_media_type, renderer_context
        if isinstance(data, bytes):
            return data
        return str(data).encode()
