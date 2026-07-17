import math
from datetime import UTC, datetime, time, timedelta

from django.contrib.auth.models import User
from django.utils import timezone

from apps.events.models import CalendarEvent, CalendarEventStatus
from apps.preferences.services import UserPreferenceService
from apps.reminders.models import Reminder, ReminderStatus
from apps.tasks.models import Task, TaskStatus
from apps.today.schemas import (
    ScheduleConflict,
    ScheduleItem,
    ScheduleItemKind,
    TodaySummary,
)
from common.time import get_timezone, to_utc


class TodayService:
    ACTIVE_TASK_STATUSES = (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
    ACTIVE_REMINDER_STATUSES = (
        ReminderStatus.PENDING,
        ReminderStatus.QUEUED,
        ReminderStatus.SENDING,
        ReminderStatus.FAILED,
    )

    @staticmethod
    def get_summary(
        *,
        user: User,
        current_at: datetime | None = None,
    ) -> TodaySummary:
        TodayService._ensure_persisted_user(user)
        generated_at = to_utc(current_at or timezone.now())
        preference = UserPreferenceService.get_or_create_for_user(user)
        user_timezone = get_timezone(preference.timezone)
        local_date = generated_at.astimezone(user_timezone).date()
        next_local_date = local_date + timedelta(days=1)
        day_start = datetime.combine(local_date, time.min, tzinfo=user_timezone).astimezone(UTC)
        day_end = datetime.combine(next_local_date, time.min, tzinfo=user_timezone).astimezone(UTC)

        events = list(
            CalendarEvent.objects.filter(
                user=user,
                start_at__lt=day_end,
                end_at__gt=day_start,
            )
            .exclude(status=CalendarEventStatus.CANCELLED)
            .order_by("start_at", "id")
        )
        active_tasks = Task.objects.filter(user=user, status__in=TodayService.ACTIVE_TASK_STATUSES)
        planned_tasks = list(
            active_tasks.filter(
                planned_start_at__lt=day_end,
                planned_end_at__gt=day_start,
            ).order_by("planned_start_at", "id")
        )
        due_tasks = list(
            active_tasks.filter(
                due_at__gte=day_start,
                due_at__lt=day_end,
            ).order_by("due_at", "id")
        )
        overdue_tasks = list(
            active_tasks.filter(due_at__lt=day_start).order_by("due_at", "id")
        )
        pending_reminders = list(
            Reminder.objects.filter(
                user=user,
                status__in=TodayService.ACTIVE_REMINDER_STATUSES,
                trigger_at__gte=day_start,
                trigger_at__lt=day_end,
            ).order_by("trigger_at", "id")
        )
        conflicts = TodayService._detect_conflicts(events, planned_tasks)
        next_event = next((event for event in events if event.start_at >= generated_at), None)
        minutes_until_next_event = (
            math.ceil((next_event.start_at - generated_at).total_seconds() / 60)
            if next_event is not None
            else None
        )

        return TodaySummary(
            date=local_date,
            timezone=preference.timezone,
            generated_at=generated_at,
            day_start_at=day_start,
            day_end_at=day_end,
            events=events,
            planned_tasks=planned_tasks,
            due_tasks=due_tasks,
            overdue_tasks=overdue_tasks,
            pending_reminders=pending_reminders,
            conflicts=conflicts,
            next_event=next_event,
            minutes_until_next_event=minutes_until_next_event,
        )

    @staticmethod
    def _detect_conflicts(
        events: list[CalendarEvent],
        planned_tasks: list[Task],
    ) -> list[ScheduleConflict]:
        items = [
            ScheduleItem(
                kind=ScheduleItemKind.EVENT,
                id=event.id,
                title=event.title,
                start_at=event.start_at,
                end_at=event.end_at,
            )
            for event in events
        ]
        items.extend(
            ScheduleItem(
                kind=ScheduleItemKind.TASK,
                id=task.id,
                title=task.title,
                start_at=task.planned_start_at,
                end_at=task.planned_end_at,
            )
            for task in planned_tasks
            if task.planned_start_at is not None and task.planned_end_at is not None
        )
        items.sort(key=lambda item: (item.start_at, item.end_at, str(item.id)))

        conflicts: list[ScheduleConflict] = []
        active: list[ScheduleItem] = []
        for item in items:
            active = [candidate for candidate in active if candidate.end_at > item.start_at]
            for candidate in active:
                overlap_start = max(candidate.start_at, item.start_at)
                overlap_end = min(candidate.end_at, item.end_at)
                if overlap_start < overlap_end:
                    conflicts.append(
                        ScheduleConflict(
                            first=candidate,
                            second=item,
                            overlap_start_at=overlap_start,
                            overlap_end_at=overlap_end,
                        )
                    )
            active.append(item)
        return conflicts

    @staticmethod
    def _ensure_persisted_user(user: User) -> None:
        if user.pk is None:
            raise ValueError("Today summary user must be persisted")
