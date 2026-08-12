import calendar
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from common.time import resolve_local_datetime, to_user_timezone, to_utc, validate_timezone

TemporalOffsetUnit = Literal["minute", "hour", "day", "week", "month"]


class AbsoluteEventTime(BaseModel):
    """An explicitly dated event interval supplied by the user."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["absolute"]
    start_at: datetime
    end_at: datetime


class RelativeEventTime(BaseModel):
    """A model-extracted relative expression, resolved only by trusted code."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["relative"]
    offset: int = Field(ge=0)
    unit: TemporalOffsetUnit
    source_text: str = Field(min_length=1, max_length=80)
    local_time: time | None = None
    duration_minutes: int = Field(ge=5, le=1440)


EventTime = Annotated[AbsoluteEventTime | RelativeEventTime, Field(discriminator="kind")]
EVENT_TIME_ADAPTER: TypeAdapter[AbsoluteEventTime | RelativeEventTime] = TypeAdapter(EventTime)


@dataclass(frozen=True, slots=True)
class TemporalResolution:
    anchor_at: datetime
    timezone: str
    specification: AbsoluteEventTime | RelativeEventTime
    start_at: datetime
    end_at: datetime

    def as_audit_payload(self) -> dict[str, object]:
        return {
            "anchor_at": self.anchor_at.isoformat(),
            "timezone": self.timezone,
            "specification": self.specification.model_dump(mode="json"),
            "start_at": self.start_at.isoformat(),
            "end_at": self.end_at.isoformat(),
            "resolved_at": self.start_at.isoformat(),
        }


class EventTemporalResolutionService:
    """Resolve an explicit event-time variant against one immutable run anchor."""

    _MAX_OFFSETS: dict[TemporalOffsetUnit, int] = {
        "minute": 525_600,
        "hour": 8_760,
        "day": 366,
        "week": 104,
        "month": 24,
    }

    @staticmethod
    def parse(value: object) -> AbsoluteEventTime | RelativeEventTime:
        """Validate the discriminated union without inferring intent from prose."""

        return EVENT_TIME_ADAPTER.validate_python(value)

    @staticmethod
    def resolve(
        *,
        anchor_at: datetime,
        timezone: str,
        specification: AbsoluteEventTime | RelativeEventTime,
    ) -> TemporalResolution:
        validate_timezone(timezone)
        anchor_utc = to_utc(anchor_at)
        if isinstance(specification, AbsoluteEventTime):
            start_at = to_utc(specification.start_at)
            end_at = to_utc(specification.end_at)
        else:
            start_at = EventTemporalResolutionService._resolve_relative_start(
                anchor_at=anchor_utc,
                timezone=timezone,
                specification=specification,
            )
            end_at = start_at + timedelta(minutes=specification.duration_minutes)
        if end_at <= start_at:
            raise ValueError("event end_at must be later than start_at")
        return TemporalResolution(
            anchor_at=anchor_utc,
            timezone=timezone,
            specification=specification,
            start_at=start_at,
            end_at=end_at,
        )

    @staticmethod
    def resolve_value(
        *,
        anchor_at: datetime,
        timezone: str,
        value: object,
    ) -> TemporalResolution:
        """Validate and resolve a raw tool payload through the same code path."""

        return EventTemporalResolutionService.resolve(
            anchor_at=anchor_at,
            timezone=timezone,
            specification=EventTemporalResolutionService.parse(value),
        )

    @staticmethod
    def _resolve_relative_start(
        *,
        anchor_at: datetime,
        timezone: str,
        specification: RelativeEventTime,
    ) -> datetime:
        source_text = specification.source_text.strip()
        if not source_text:
            raise ValueError("relative time source_text cannot be empty")
        maximum = EventTemporalResolutionService._MAX_OFFSETS[specification.unit]
        if specification.offset > maximum:
            raise ValueError(f"relative {specification.unit} offset is out of range")
        if specification.unit in {"minute", "hour"}:
            if specification.local_time is not None:
                raise ValueError("local_time is only valid for day, week, or month offsets")
            delta = (
                timedelta(minutes=specification.offset)
                if specification.unit == "minute"
                else timedelta(hours=specification.offset)
            )
            return anchor_at + delta

        local_anchor = to_user_timezone(anchor_at, timezone)
        if specification.unit == "day":
            target_date = local_anchor.date() + timedelta(days=specification.offset)
        elif specification.unit == "week":
            target_date = local_anchor.date() + timedelta(weeks=specification.offset)
        else:
            month_index = local_anchor.month - 1 + specification.offset
            target_year = local_anchor.year + month_index // 12
            target_month = month_index % 12 + 1
            target_day = min(local_anchor.day, calendar.monthrange(target_year, target_month)[1])
            target_date = local_anchor.date().replace(
                year=target_year,
                month=target_month,
                day=target_day,
            )
        target_time = specification.local_time or local_anchor.time().replace(tzinfo=None)
        local_target = datetime.combine(target_date, target_time.replace(tzinfo=None))
        return resolve_local_datetime(local_target, timezone).astimezone(UTC)
