from dataclasses import dataclass, field
from datetime import datetime

from django.contrib.auth.models import User

from apps.agents.triggers import TriggerType
from common.time import to_utc, validate_timezone


@dataclass(frozen=True, slots=True, kw_only=True)
class RuntimeContext:
    """Immutable dependencies and metadata scoped to one graph invocation."""

    user_id: str
    request_id: str
    timezone: str
    locale: str
    current_datetime: datetime
    trigger_type: TriggerType
    conversation_id: str | None = None
    agent_run_id: str | None = None
    read_only: bool = False
    actor: User | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        for field_name in ("user_id", "request_id", "timezone", "locale"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")
        if self.conversation_id is not None and not self.conversation_id.strip():
            raise ValueError("conversation_id cannot be empty")
        if self.agent_run_id is not None and not self.agent_run_id.strip():
            raise ValueError("agent_run_id cannot be empty")
        if self.actor is not None:
            if self.actor.pk is None:
                raise ValueError("actor must be persisted")
            if str(self.actor.pk) != self.user_id:
                raise ValueError("actor primary key must match user_id")

        validate_timezone(self.timezone)
        object.__setattr__(self, "current_datetime", to_utc(self.current_datetime))
