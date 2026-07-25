from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from django.contrib.auth.models import User
from langchain.tools import ToolRuntime

from apps.agents.context import RuntimeContext


class MissingActorError(PermissionError):
    pass


class ReadOnlyRunError(PermissionError):
    pass


def require_actor(runtime: ToolRuntime[RuntimeContext, Any]) -> User:
    actor = runtime.context.actor
    if actor is None:
        raise MissingActorError("This tool requires a trusted authenticated actor")
    return actor


def require_writable(runtime: ToolRuntime[RuntimeContext, Any]) -> User:
    actor = require_actor(runtime)
    if runtime.context.read_only:
        raise ReadOnlyRunError("Write tools are disabled for this run")
    return actor


def tool_idempotency_key(runtime: ToolRuntime[RuntimeContext, Any], *, purpose: str) -> str:
    """Build an opaque idempotency key from trusted run and tool-call identity.

    The model never supplies idempotency keys; retries of the same tool call use
    the same key while a later request has a different call id.
    """

    context = runtime.context
    run_id = context.agent_run_id or context.conversation_id or "interactive"
    call_id = str(getattr(runtime, "tool_call_id", "") or "single")
    return f"agent:{run_id}:{purpose}:{call_id}"[:128]


def json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return json_value(value.value)
    if isinstance(value, Mapping):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [json_value(item) for item in value]
    return value


def model_dict(instance: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: json_value(getattr(instance, field)) for field in fields}
