from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.events.models import CalendarEvent, CalendarEventStatus
from apps.preferences.services import UserPreferenceService
from apps.reminders.models import (
    Reminder,
    ReminderScheduleAnchor,
    ReminderStatus,
    ReminderTargetType,
)
from apps.tasks.models import Task, TaskStatus


class ReminderScheduleService:
    """Maintain deterministic, future reminders for planned work and events."""

    TASK_OFFSETS = (10_080, 4_320, 1_440, 30)
    EVENT_OFFSETS = (1_440, 120, 30)
    ACTIVE_STATUSES = (ReminderStatus.PENDING, ReminderStatus.QUEUED, ReminderStatus.FAILED)

    @classmethod
    def sync_task_reminders(cls, *, task: Task) -> None:
        if task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED} or not task.planned_start_at:
            cls.cancel_task_reminders(task=task)
            return
        cls._sync(
            user=task.user,
            target_type=ReminderTargetType.TASK,
            target_id=task.id,
            title=task.title,
            timezone_name=UserPreferenceService.get_or_create_for_user(task.user).timezone,
            anchor=ReminderScheduleAnchor.TASK_PLANNED_START,
            starts_at=task.planned_start_at,
            offsets=cls.TASK_OFFSETS,
        )

    @classmethod
    def sync_event_reminders(cls, *, event: CalendarEvent) -> None:
        if event.status == CalendarEventStatus.CANCELLED:
            cls.cancel_event_reminders(event=event)
            return
        cls._sync(
            user=event.user,
            target_type=ReminderTargetType.CALENDAR_EVENT,
            target_id=event.id,
            title=event.title,
            timezone_name=event.timezone,
            anchor=ReminderScheduleAnchor.EVENT_START,
            starts_at=event.start_at,
            offsets=cls.EVENT_OFFSETS,
        )

    @classmethod
    def cancel_task_reminders(cls, *, task: Task) -> None:
        cls._cancel(target_type=ReminderTargetType.TASK, target_id=task.id)

    @classmethod
    def cancel_event_reminders(cls, *, event: CalendarEvent) -> None:
        cls._cancel(target_type=ReminderTargetType.CALENDAR_EVENT, target_id=event.id)

    @classmethod
    @transaction.atomic
    def _sync(
        cls,
        *,
        user: object,
        target_type: str,
        target_id: object,
        title: str,
        timezone_name: str,
        anchor: str,
        starts_at: object,
        offsets: tuple[int, ...],
    ) -> None:
        now = timezone.now()
        desired = {
            offset: starts_at - timedelta(minutes=offset)
            for offset in offsets
            if starts_at - timedelta(minutes=offset) > now
        }
        existing = {
            reminder.offset_minutes: reminder
            for reminder in Reminder.objects.select_for_update().filter(
                user=user,
                target_type=target_type,
                target_id=target_id,
                schedule_anchor=anchor,
            )
        }
        for offset, trigger_at in desired.items():
            reminder = existing.pop(offset, None)
            if reminder is None:
                Reminder.objects.create(
                    user=user,
                    target_type=target_type,
                    target_id=target_id,
                    title=title,
                    trigger_at=trigger_at,
                    timezone=timezone_name,
                    schedule_anchor=anchor,
                    offset_minutes=offset,
                    deduplication_key=f"schedule:{target_type}:{target_id}:{anchor}:{offset}",
                )
            elif reminder.status in cls.ACTIVE_STATUSES:
                reminder.title = title
                reminder.trigger_at = trigger_at
                reminder.timezone = timezone_name
                reminder.save(update_fields=["title", "trigger_at", "timezone", "updated_at"])
        for reminder in existing.values():
            if reminder.status in cls.ACTIVE_STATUSES:
                reminder.status = ReminderStatus.CANCELLED
                reminder.save(update_fields=["status", "updated_at"])

    @classmethod
    @transaction.atomic
    def _cancel(cls, *, target_type: str, target_id: object) -> None:
        Reminder.objects.select_for_update().filter(
            target_type=target_type,
            target_id=target_id,
            schedule_anchor__gt="",
            status__in=cls.ACTIVE_STATUSES,
        ).update(status=ReminderStatus.CANCELLED)
