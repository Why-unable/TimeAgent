from dataclasses import dataclass, field
from datetime import datetime, time


@dataclass(frozen=True, slots=True)
class TimeSlot:
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True, slots=True)
class PlanningConstraints:
    timezone: str | None = None
    daily_start: time | None = None
    daily_end: time | None = None
    allowed_weekdays: tuple[int, ...] = field(default_factory=lambda: tuple(range(7)))
    slot_increment_minutes: int = 15
    max_results: int | None = None
    include_planned_tasks: bool = True

    def validate(self) -> None:
        if (self.daily_start is None) != (self.daily_end is None):
            raise ValueError("daily_start and daily_end must be provided together")
        if (
            self.daily_start is not None
            and self.daily_end is not None
            and self.daily_end <= self.daily_start
        ):
            raise ValueError("daily_end must be later than daily_start")
        if not self.allowed_weekdays:
            raise ValueError("allowed_weekdays cannot be empty")
        if len(set(self.allowed_weekdays)) != len(self.allowed_weekdays) or any(
            weekday < 0 or weekday > 6 for weekday in self.allowed_weekdays
        ):
            raise ValueError("allowed_weekdays must contain unique values from 0 to 6")
        if self.slot_increment_minutes < 1:
            raise ValueError("slot_increment_minutes must be positive")
        if self.max_results is not None and self.max_results < 1:
            raise ValueError("max_results must be positive")
