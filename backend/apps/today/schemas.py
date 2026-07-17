from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from apps.events.models import CalendarEvent
from apps.reminders.models import Reminder
from apps.tasks.models import Task


class ScheduleItemKind(StrEnum):
    EVENT = "event"
    TASK = "task"


@dataclass(frozen=True, slots=True)
class ScheduleItem:
    kind: ScheduleItemKind
    id: UUID
    title: str
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True, slots=True)
class ScheduleConflict:
    first: ScheduleItem
    second: ScheduleItem
    overlap_start_at: datetime
    overlap_end_at: datetime


@dataclass(frozen=True, slots=True)
class TodaySummary:
    date: date
    timezone: str
    generated_at: datetime
    day_start_at: datetime
    day_end_at: datetime
    events: list[CalendarEvent]
    planned_tasks: list[Task]
    due_tasks: list[Task]
    overdue_tasks: list[Task]
    pending_reminders: list[Reminder]
    conflicts: list[ScheduleConflict]
    next_event: CalendarEvent | None
    minutes_until_next_event: int | None
