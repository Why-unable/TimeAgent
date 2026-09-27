from dataclasses import dataclass, field
from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TaskScheduleDecision(BaseModel):
    """Structured schedule intent proposed by the Time Steward LLM."""

    model_config = ConfigDict(extra="forbid")

    task_id: UUID = Field(description="所选排程任务的 UUID。")
    preferred_start_at: datetime | None = Field(
        default=None,
        description=(
            "带时区的软目标开始时间；规划器会从可行时段中选择最接近者，"
            "可能受日历、工作时间和截止日调整。"
        ),
    )
    earliest_start_at: datetime | None = Field(
        default=None,
        description="带时区的硬性最早开始时间；只用于用户明确给出或确认的限制。",
    )
    latest_end_at: datetime | None = Field(
        default=None,
        description="带时区的硬性最晚结束时间；只用于用户明确给出或确认的限制。",
    )
    predecessor_task_ids: list[UUID] = Field(
        default_factory=list,
        description="该任务必须先完成的同一排程计划内任务 UUID。",
    )
    minimum_gap_days: int = Field(
        default=0,
        ge=0,
        le=30,
        description="前置任务结束后至少等待的完整 24 小时天数；仅按用户明确要求填写。",
    )
    rationale: str = Field(
        default="",
        max_length=240,
        description="可展示给用户的简短安排依据；不要写私有推理。",
    )

    @field_validator("preferred_start_at", "earliest_start_at", "latest_end_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("Schedule decision datetimes must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_relationships(self) -> "TaskScheduleDecision":
        if len(set(self.predecessor_task_ids)) != len(self.predecessor_task_ids):
            raise ValueError("predecessor_task_ids must be unique")
        if self.task_id in self.predecessor_task_ids:
            raise ValueError("A task cannot depend on itself")
        if self.minimum_gap_days and not self.predecessor_task_ids:
            raise ValueError("minimum_gap_days requires at least one predecessor")
        if (
            self.earliest_start_at is not None
            and self.latest_end_at is not None
            and self.latest_end_at <= self.earliest_start_at
        ):
            raise ValueError("latest_end_at must be later than earliest_start_at")
        return self


class DailyAvailabilityWindow(BaseModel):
    """A date-bounded daily work window explicitly requested for one plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start_date: date = Field(description="用户时区内生效的首日，包含该日期。")
    end_date: date = Field(description="用户时区内生效的末日，包含该日期。")
    daily_start: time = Field(description="这些日期中每天最早可排的本地时间。")
    daily_end: time = Field(description="这些日期中每天最晚可排到的本地时间。")

    @model_validator(mode="after")
    def validate_window(self) -> "DailyAvailabilityWindow":
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if self.daily_end <= self.daily_start:
            raise ValueError("daily_end must be later than daily_start")
        return self


class SchedulePlanItemEdit(BaseModel):
    """One typed edit to an existing reviewable schedule draft."""

    model_config = ConfigDict(extra="forbid")

    task_id: UUID = Field(description="草案中的任务 ID。")
    start_at: datetime | None = Field(
        default=None,
        description="新的带时区开始时间；移动任务时必须与 end_at 同时提供。",
    )
    end_at: datetime | None = Field(
        default=None,
        description="新的带时区结束时间；移动任务时必须与 start_at 同时提供。",
    )
    locked: bool | None = Field(default=None, description="是否锁定此草案项，避免后续重生成移动。")

    @field_validator("start_at", "end_at")
    @classmethod
    def require_aware_edit_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("Schedule plan edit times must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_edit_shape(self) -> "SchedulePlanItemEdit":
        if (self.start_at is None) != (self.end_at is None):
            raise ValueError("start_at and end_at must be provided together")
        if self.start_at is not None and self.end_at is not None and self.end_at <= self.start_at:
            raise ValueError("end_at must be later than start_at")
        if self.start_at is None and self.locked is None:
            raise ValueError("An edit must move or lock/unlock a schedule plan item")
        return self


@dataclass(frozen=True, slots=True)
class TimeSlot:
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True, slots=True)
class PlanningConstraints:
    timezone: str | None = None
    daily_start: time | None = None
    daily_end: time | None = None
    allowed_weekdays: tuple[int, ...] = field(default_factory=lambda: tuple(range(5)))
    slot_increment_minutes: int = 15
    max_results: int | None = None
    include_planned_tasks: bool = True
    daily_worktime_overrides: tuple[DailyAvailabilityWindow, ...] = ()

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
        windows = sorted(self.daily_worktime_overrides, key=lambda item: item.start_date)
        if any(
            current.start_date <= previous.end_date
            for previous, current in zip(windows, windows[1:], strict=False)
        ):
            raise ValueError("availability windows must not overlap")
