from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model

from apps.events.services import CreateEventCommand, EventService, UpdateEventCommand
from apps.reminders.models import Reminder, ReminderStatus, ReminderTargetType
from apps.tasks.services import CreateTaskCommand, TaskService

pytestmark = pytest.mark.django_db


def test_planned_task_creates_standard_future_reminders() -> None:
    user = get_user_model().objects.create_user(username="schedule-task")
    start = datetime.now(UTC) + timedelta(days=10)
    TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Write report",
            planned_start_at=start,
            planned_end_at=start + timedelta(hours=1),
        )
    )

    reminders = Reminder.objects.filter(user=user, target_type=ReminderTargetType.TASK)
    assert set(reminders.values_list("offset_minutes", flat=True)) == {0, 15, 1440}


def test_near_term_event_skips_relative_reminders_whose_trigger_time_has_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = get_user_model().objects.create_user(username="near-term-event")
    now = datetime(2026, 8, 12, 4, tzinfo=UTC)
    start = now + timedelta(hours=2)
    monkeypatch.setattr("apps.reminders.scheduling.timezone.now", lambda: now)

    event = EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Near-term review",
            start_at=start,
            end_at=start + timedelta(hours=1),
            timezone="Asia/Shanghai",
        )
    )

    reminders = Reminder.objects.filter(target_id=event.id)
    assert set(reminders.values_list("offset_minutes", flat=True)) == {0, 15}
    assert not reminders.filter(offset_minutes=1_440).exists()


def test_reschedule_cancels_automatic_offsets_that_are_no_longer_in_the_future(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = get_user_model().objects.create_user(username="near-term-reschedule")
    now = datetime(2026, 8, 12, 4, tzinfo=UTC)
    monkeypatch.setattr("apps.reminders.scheduling.timezone.now", lambda: now)
    original_start = now + timedelta(days=2)
    event = EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Rescheduled review",
            start_at=original_start,
            end_at=original_start + timedelta(hours=1),
            timezone="Asia/Shanghai",
        )
    )

    new_start = now + timedelta(hours=2)
    EventService.update_event(
        UpdateEventCommand(
            user=user,
            event_id=event.id,
            expected_version=event.version,
            changes={"start_at": new_start, "end_at": new_start + timedelta(hours=1)},
            current_datetime=now,
        )
    )

    reminders = Reminder.objects.filter(target_id=event.id)
    assert set(
        reminders.filter(status=ReminderStatus.PENDING).values_list(
            "offset_minutes",
            flat=True,
        )
    ) == {0, 15}
    assert reminders.get(offset_minutes=1_440).status == ReminderStatus.CANCELLED


def test_event_reschedule_updates_its_pending_reminders() -> None:
    user = get_user_model().objects.create_user(username="schedule-event")
    start = datetime.now(UTC) + timedelta(days=3)
    event = EventService.create_event(
        CreateEventCommand(
            user=user,
            created_by=user,
            title="Review",
            start_at=start,
            end_at=start + timedelta(hours=1),
            timezone="Asia/Shanghai",
        )
    )
    new_start = start + timedelta(days=1)
    EventService.update_event(
        UpdateEventCommand(
            user=user,
            event_id=event.id,
            expected_version=event.version,
            changes={"start_at": new_start, "end_at": new_start + timedelta(hours=1)},
        )
    )
    reminder = Reminder.objects.get(target_id=event.id, offset_minutes=15)
    assert reminder.trigger_at == new_start - timedelta(minutes=15)


def test_task_reschedule_updates_its_pending_reminders() -> None:
    user = get_user_model().objects.create_user(username="schedule-task-reschedule")
    start = datetime.now(UTC) + timedelta(days=10)
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Prepare workshop",
            planned_start_at=start,
            planned_end_at=start + timedelta(hours=2),
        )
    )

    new_start = start + timedelta(days=2)
    TaskService.reschedule_task(
        task_id=task.id,
        user=user,
        planned_start_at=new_start,
        planned_end_at=new_start + timedelta(hours=2),
    )

    reminder = Reminder.objects.get(target_id=task.id, offset_minutes=1_440)
    assert reminder.trigger_at == new_start - timedelta(days=1)


def test_cancelled_event_cancels_pending_automatic_reminders() -> None:
    user = get_user_model().objects.create_user(username="schedule-cancel")
    start = datetime.now(UTC) + timedelta(days=2)
    event = EventService.create_event(
        CreateEventCommand(
            user=user,
            created_by=user,
            title="Review",
            start_at=start,
            end_at=start + timedelta(hours=1),
            timezone="Asia/Shanghai",
        )
    )
    EventService.cancel_event(event_id=event.id, user=user, expected_version=event.version)
    assert (
        not Reminder.objects.filter(target_id=event.id)
        .exclude(status=ReminderStatus.CANCELLED)
        .exists()
    )
