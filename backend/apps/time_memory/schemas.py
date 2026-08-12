from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WindowName = Literal["7d", "30d", "180d"]


class CommonPlace(BaseModel):
    model_config = ConfigDict(extra="ignore")

    place_id: str = ""
    name: str
    normalized_name: str = ""
    event_count: int = Field(ge=1)
    total_scheduled_hours: float = Field(default=0, ge=0)
    typical_weekdays: list[int] = Field(default_factory=list)
    typical_time_ranges: list[str] = Field(default_factory=list)
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    score: float = Field(default=0, ge=0, le=1)


class SchedulePattern(BaseModel):
    total_scheduled_hours: float = Field(default=0, ge=0)
    average_daily_scheduled_hours: float = Field(default=0, ge=0)
    median_daily_scheduled_hours: float = Field(default=0, ge=0)
    scheduled_day_count: int = Field(default=0, ge=0)
    busy_day_count: int = Field(default=0, ge=0)
    light_day_count: int = Field(default=0, ge=0)
    rest_day_count: int = Field(default=0, ge=0)
    consecutive_busy_days_max: int = Field(default=0, ge=0)
    weekday_average_hours: float = Field(default=0, ge=0)
    weekend_average_hours: float = Field(default=0, ge=0)
    peak_time_ranges: list[str] = Field(default_factory=list)
    work_rest_balance: Literal["balanced", "slightly_busy", "overloaded", "insufficient_data"] = (
        "insufficient_data"
    )
    summary: str = ""


class PlanningPattern(BaseModel):
    created_event_count: int = Field(default=0, ge=0)
    creation_session_count: int = Field(default=0, ge=0)
    batch_creation_session_count: int = Field(default=0, ge=0)
    batch_creation_ratio: float = Field(default=0, ge=0, le=1)
    incremental_creation_ratio: float = Field(default=0, ge=0, le=1)
    average_lead_time_hours: float = 0
    median_lead_time_hours: float = 0
    last_minute_creation_ratio: float = Field(default=0, ge=0, le=1)
    long_horizon_creation_ratio: float = Field(default=0, ge=0, le=1)
    typical_creation_time_ranges: list[str] = Field(default_factory=list)
    planning_style: Literal["batch", "incremental", "mixed", "insufficient_data"] = (
        "insufficient_data"
    )
    summary: str = ""


class ChangePattern(BaseModel):
    modified_event_count: int = Field(default=0, ge=0)
    rescheduled_event_count: int = Field(default=0, ge=0)
    postponed_event_count: int = Field(default=0, ge=0)
    advanced_event_count: int = Field(default=0, ge=0)
    cancelled_event_count: int = Field(default=0, ge=0)
    completed_event_count: int = Field(default=0, ge=0)
    reschedule_ratio: float = Field(default=0, ge=0, le=1)
    postpone_ratio: float = Field(default=0, ge=0, le=1)
    cancellation_ratio: float = Field(default=0, ge=0, le=1)
    completion_ratio: float | None = None
    average_reschedule_delta_hours: float = 0
    dominant_change_behavior: Literal[
        "stable",
        "postpone",
        "advance",
        "cancel",
        "frequent_adjustment",
        "insufficient_data",
    ] = "insufficient_data"
    summary: str = ""


class BehaviorWindow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    window: WindowName
    start_date: date
    end_date: date
    sample_days: int = Field(ge=1)
    event_count: int = Field(ge=0)
    task_count: int = Field(default=0, ge=0)
    reminder_count: int = Field(default=0, ge=0)
    completed_task_count: int = Field(default=0, ge=0)
    cancelled_task_count: int = Field(default=0, ge=0)
    source_distribution: dict[str, int] = Field(default_factory=dict)
    schedule_pattern: SchedulePattern = Field(default_factory=SchedulePattern)
    planning_pattern: PlanningPattern = Field(default_factory=PlanningPattern)
    change_pattern: ChangePattern = Field(default_factory=ChangePattern)
    summary: str = ""
    confidence: float = Field(default=0, ge=0, le=1)


class StablePattern(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pattern_id: str
    pattern_type: Literal["schedule", "planning", "change", "place"]
    summary: str
    evidence_windows: list[WindowName] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    first_detected_at: datetime
    last_confirmed_at: datetime
    unsupported_rebuild_count: int = Field(default=0, ge=0)
    status: Literal["active", "weakening", "expired"] = "active"
    score: float = Field(default=0, ge=0, le=1)

    @property
    def key(self) -> str:
        return self.pattern_id

    @property
    def category(self) -> str:
        return self.pattern_type

    @property
    def evidence_count(self) -> int:
        return len(self.evidence_windows)


class TimeMemoryProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: int = Field(default=2, ge=1)
    user_id: str
    generated_at: datetime
    data_until: datetime
    timezone: str
    common_places: list[CommonPlace] = Field(default_factory=list)
    behavior_windows: dict[WindowName, BehaviorWindow]
    stable_patterns: list[StablePattern] = Field(default_factory=list)
    profile_summary: str = ""
    version: int = Field(ge=1)
