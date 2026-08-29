from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from common.time import to_utc, validate_timezone


@dataclass(frozen=True, slots=True)
class TemporalContextSnapshot:
    """A deterministic, explicit time boundary shared by planning workflows."""

    now_utc: datetime
    timezone: str
    local_date: date
    day_start_utc: datetime
    day_end_utc: datetime

    @classmethod
    def build(cls, *, now: datetime, timezone_name: str) -> "TemporalContextSnapshot":
        validate_timezone(timezone_name)
        now_utc = to_utc(now)
        user_timezone = ZoneInfo(timezone_name)
        local_date = now_utc.astimezone(user_timezone).date()
        day_start = datetime.combine(local_date, time.min, tzinfo=user_timezone).astimezone(UTC)
        day_end = (
            datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=user_timezone)
            .astimezone(UTC)
        )
        return cls(
            now_utc=now_utc,
            timezone=timezone_name,
            local_date=local_date,
            day_start_utc=day_start,
            day_end_utc=day_end,
        )
