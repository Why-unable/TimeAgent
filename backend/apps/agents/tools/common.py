from datetime import date, datetime, time
from typing import Any

from django.contrib.auth.models import User
from langchain.tools import ToolRuntime

from apps.agents.context import RuntimeContext


class MissingActorError(PermissionError):
    pass


class ReadOnlyRunError(PermissionError):
    pass


def require_actor(runtime: ToolRuntime[RuntimeContext]) -> User:
    actor = runtime.context.actor
    if actor is None:
        raise MissingActorError("This tool requires a trusted authenticated actor")
    return actor


def require_writable(runtime: ToolRuntime[RuntimeContext]) -> User:
    actor = require_actor(runtime)
    if runtime.context.read_only:
        raise ReadOnlyRunError("Write tools are disabled for this run")
    return actor


def json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value


def model_dict(instance: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: json_value(getattr(instance, field)) for field in fields}
