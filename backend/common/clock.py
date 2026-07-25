from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Trusted source of the current UTC instant."""

    def now_utc(self) -> datetime: ...


class SystemClock:
    """Production clock backed by the application host's UTC clock."""

    def now_utc(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """Test clock returning one explicit UTC instant."""

    def __init__(self, current_datetime: datetime) -> None:
        if current_datetime.tzinfo is None or current_datetime.utcoffset() is None:
            raise ValueError("FixedClock requires a timezone-aware datetime")
        self._current_datetime = current_datetime.astimezone(UTC)

    def now_utc(self) -> datetime:
        return self._current_datetime
