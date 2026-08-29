from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from common.time import NaiveDateTimeError, to_utc, validate_timezone


class CalendarDTO(BaseModel):
    model_config = ConfigDict(frozen=True)


class ExternalCalendarContext(CalendarDTO):
    account_reference: str = Field(min_length=1, max_length=255)
    timezone: str

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        validate_timezone(value)
        return value


class ExternalCalendarSummary(CalendarDTO):
    external_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    timezone: str
    is_primary: bool = False
    read_only: bool = True

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        validate_timezone(value)
        return value


class ExternalEventQuery(CalendarDTO):
    calendar_id: str = Field(min_length=1, max_length=255)
    starts_at_or_after: datetime
    starts_before: datetime
    sync_cursor: str = ""

    @model_validator(mode="after")
    def normalize_range(self) -> "ExternalEventQuery":
        try:
            start = to_utc(self.starts_at_or_after)
            end = to_utc(self.starts_before)
        except NaiveDateTimeError as exc:
            raise ValueError("External event query datetimes must be timezone-aware") from exc
        if start >= end:
            raise ValueError("starts_before must be later than starts_at_or_after")
        object.__setattr__(self, "starts_at_or_after", start)
        object.__setattr__(self, "starts_before", end)
        return self


class ExternalEvent(CalendarDTO):
    external_id: str = Field(min_length=1, max_length=255)
    calendar_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    starts_at: datetime
    ends_at: datetime
    timezone: str
    description: str = ""
    location: str = ""
    status: str = "confirmed"
    etag: str = ""

    @model_validator(mode="after")
    def normalize_times(self) -> "ExternalEvent":
        validate_timezone(self.timezone)
        try:
            start = to_utc(self.starts_at)
            end = to_utc(self.ends_at)
        except NaiveDateTimeError as exc:
            raise ValueError("External event datetimes must be timezone-aware") from exc
        if start >= end:
            raise ValueError("ends_at must be later than starts_at")
        object.__setattr__(self, "starts_at", start)
        object.__setattr__(self, "ends_at", end)
        return self


class ExternalEventTombstone(CalendarDTO):
    external_id: str = Field(min_length=1, max_length=255)
    calendar_id: str = Field(min_length=1, max_length=255)


class ExternalEventPage(CalendarDTO):
    events: tuple[ExternalEvent | ExternalEventTombstone, ...]
    next_sync_cursor: str = ""
    cursor_was_reset: bool = False


class ExternalEventCreate(CalendarDTO):
    calendar_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    starts_at: datetime
    ends_at: datetime
    timezone: str
    description: str = ""
    location: str = ""

    @model_validator(mode="after")
    def validate_times(self) -> "ExternalEventCreate":
        validate_timezone(self.timezone)
        try:
            if to_utc(self.starts_at) >= to_utc(self.ends_at):
                raise ValueError("ends_at must be later than starts_at")
        except NaiveDateTimeError as exc:
            raise ValueError("External event datetimes must be timezone-aware") from exc
        return self


class ExternalEventUpdate(CalendarDTO):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    timezone: str | None = None
    description: str | None = None
    location: str | None = None

    @model_validator(mode="after")
    def validate_partial_times(self) -> "ExternalEventUpdate":
        if self.timezone:
            validate_timezone(self.timezone)
        for value in (self.starts_at, self.ends_at):
            if value is not None:
                try:
                    to_utc(value)
                except NaiveDateTimeError as exc:
                    raise ValueError("External event datetimes must be timezone-aware") from exc
        if self.starts_at is not None and self.ends_at is not None:
            if to_utc(self.starts_at) >= to_utc(self.ends_at):
                raise ValueError("ends_at must be later than starts_at")
        return self
