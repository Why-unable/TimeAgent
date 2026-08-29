from dataclasses import dataclass
from datetime import datetime

from django.contrib.auth.models import User
from django.db import models

from apps.events.models import CalendarEvent
from apps.reminders.models import Reminder
from apps.tasks.models import Task, TaskExecutionSignal
from apps.time_memory.models import ScheduleChange


@dataclass(frozen=True, slots=True)
class TimeMemorySourceData:
    events: tuple[CalendarEvent, ...] = ()
    tasks: tuple[Task, ...] = ()
    reminders: tuple[Reminder, ...] = ()
    changes: tuple[ScheduleChange, ...] = ()
    execution_signals: tuple[TaskExecutionSignal, ...] = ()


class TimeMemorySourceRepository:
    @staticmethod
    def load(
        *,
        user: User,
        since: datetime,
        until: datetime,
    ) -> TimeMemorySourceData:
        events = CalendarEvent.objects.filter(
            user=user,
            end_at__gte=since,
            start_at__lte=until,
        ).select_related("task")
        tasks = (
            Task.objects.filter(user=user)
            .filter(
                created_at__lte=until,
            )
            .filter(
                models.Q(created_at__gte=since)
                | models.Q(completed_at__gte=since)
                | models.Q(planned_end_at__gte=since)
            )
        )
        changes = ScheduleChange.objects.filter(
            user=user,
            occurred_at__gte=since,
            occurred_at__lte=until,
        )
        reminders = Reminder.objects.filter(
            user=user,
            created_at__gte=since,
            created_at__lte=until,
        )
        execution_signals = TaskExecutionSignal.objects.filter(
            user=user,
            occurred_at__gte=since,
            occurred_at__lte=until,
        )
        return TimeMemorySourceData(
            events=tuple(events),
            tasks=tuple(tasks),
            reminders=tuple(reminders),
            changes=tuple(changes),
            execution_signals=tuple(execution_signals),
        )
