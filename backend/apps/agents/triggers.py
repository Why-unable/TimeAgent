from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, field_validator

from common.time import to_utc

type TriggerType = Literal[
    "user_message",
    "manual_briefing",
    "scheduled_briefing",
    "reminder_due",
    "calendar_webhook",
]


class TriggerEnvelope(BaseModel):
    """Validated, transport-neutral input for the outer graph."""

    model_config = ConfigDict(extra="forbid")

    trigger_type: TriggerType
    user_id: UUID
    operation_id: UUID
    conversation_id: UUID | None = None
    payload: dict[str, JsonValue]
    triggered_at: datetime

    @field_validator("triggered_at")
    @classmethod
    def normalize_triggered_at(cls, value: datetime) -> datetime:
        return to_utc(value)
