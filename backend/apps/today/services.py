import math
from datetime import datetime

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
    TodayExecutionItem,
    TodaySummary,
)
from common.temporal_context import TemporalContextSnapshot


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
        preference = UserPreferenceService.get_or_create_for_user(user)
        temporal = TemporalContextSnapshot.build(
            now=current_at or timezone.now(),
            timezone_name=preference.timezone,
        )
        generated_at = temporal.now_utc
        local_date = temporal.local_date
        day_start = temporal.day_start_utc
        day_end = temporal.day_end_utc

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
        overdue_tasks = list(active_tasks.filter(due_at__lt=day_start).order_by("due_at", "id"))
        in_progress_tasks = list(
            Task.objects.filter(user=user, status=TaskStatus.IN_PROGRESS).order_by(
                "actual_started_at", "id"
            )
        )
        unfinished_by_id = {
            task.pk: task
            for task in [*planned_tasks, *due_tasks, *overdue_tasks, *in_progress_tasks]
        }
        unfinished_tasks = sorted(
            unfinished_by_id.values(),
            key=lambda task: (task.due_at or day_end, task.title, str(task.pk)),
        )
        completed_tasks = list(
            Task.objects.filter(
                user=user,
                status=TaskStatus.COMPLETED,
                completed_at__gte=day_start,
                completed_at__lt=day_end,
            ).order_by("completed_at", "id")
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
        execution_now, execution_next, execution_later = TodayService._execution_surface(
            events=events,
            planned_tasks=planned_tasks,
            due_tasks=due_tasks,
            overdue_tasks=overdue_tasks,
            in_progress_tasks=in_progress_tasks,
            current_at=generated_at,
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
            unfinished_tasks=unfinished_tasks,
            completed_tasks=completed_tasks,
            pending_reminders=pending_reminders,
            conflicts=conflicts,
            next_event=next_event,
            minutes_until_next_event=minutes_until_next_event,
            execution_now=execution_now,
            execution_next=execution_next,
            execution_later=execution_later,
        )

    @staticmethod
    def _execution_surface(
        *,
        events: list[CalendarEvent],
        planned_tasks: list[Task],
        due_tasks: list[Task],
        overdue_tasks: list[Task],
        in_progress_tasks: list[Task],
        current_at: datetime,
    ) -> tuple[list[TodayExecutionItem], list[TodayExecutionItem], list[TodayExecutionItem]]:
        scheduled: list[TodayExecutionItem] = [
            TodayExecutionItem(
                kind=ScheduleItemKind.EVENT,
                id=event.pk,
                title=event.title,
                start_at=event.start_at,
                end_at=event.end_at,
                status=None,
            )
            for event in events
        ]
        scheduled.extend(
            TodayExecutionItem(
                kind=ScheduleItemKind.TASK,
                id=task.pk,
                title=task.title,
                start_at=task.planned_start_at,
                end_at=task.planned_end_at,
                status=task.status,
                due_at=task.due_at,
            )
            for task in planned_tasks
            if task.planned_start_at is not None and task.planned_end_at is not None
        )

        now_items: dict[tuple[ScheduleItemKind, object], TodayExecutionItem] = {
            (item.kind, item.id): item
            for item in scheduled
            if item.start_at is not None
            and item.end_at is not None
            and item.start_at <= current_at < item.end_at
        }
        in_progress_ids = {task.pk for task in in_progress_tasks}
        for task in in_progress_tasks:
            key = (ScheduleItemKind.TASK, task.pk)
            now_items[key] = TodayExecutionItem(
                kind=ScheduleItemKind.TASK,
                id=task.pk,
                title=task.title,
                start_at=task.actual_started_at,
                end_at=None,
                status=task.status,
                due_at=task.due_at,
            )

        scheduled_ids = {item.id for item in scheduled if item.kind == ScheduleItemKind.TASK}
        future = sorted(
            (
                item
                for item in scheduled
                if item.start_at is not None
                and item.start_at > current_at
                and not (item.kind == ScheduleItemKind.TASK and item.id in in_progress_ids)
            ),
            key=lambda item: (item.start_at or current_at, str(item.id)),
        )
        next_start = future[0].start_at if future else None
        next_items = [item for item in future if item.start_at == next_start]
        next_keys = {(item.kind, item.id) for item in next_items}
        now_keys = set(now_items)
        later_items = [
            item
            for item in future
            if (item.kind, item.id) not in next_keys and (item.kind, item.id) not in now_keys
        ]
        later_items.extend(
            item
            for item in scheduled
            if item.kind == ScheduleItemKind.TASK
            and item.id not in in_progress_ids
            and item.start_at is not None
            and item.end_at is not None
            and item.end_at <= current_at
        )

        unscheduled_tasks = sorted(
            {
                task.pk: task
                for task in [*due_tasks, *overdue_tasks]
                if task.pk not in scheduled_ids and task.pk not in in_progress_ids
            }.values(),
            key=lambda task: (task.due_at or current_at, str(task.pk)),
        )
        later_items.extend(
            TodayExecutionItem(
                kind=ScheduleItemKind.TASK,
                id=task.pk,
                title=task.title,
                start_at=None,
                end_at=None,
                status=task.status,
                due_at=task.due_at,
            )
            for task in unscheduled_tasks
        )
        later_items.sort(
            key=lambda item: (item.start_at or item.due_at or current_at, str(item.id))
        )
        return list(now_items.values()), next_items, later_items

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
