from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User

from apps.notifications.models import NotificationDelivery, NotificationDeliveryStatus
from apps.reminders.dispatcher import ReminderDeliveryError, ReminderDispatcher
from apps.reminders.models import Reminder, ReminderStatus
from apps.reminders.services import CreateReminderCommand, ReminderService

pytestmark = pytest.mark.django_db

FIXED_NOW = datetime(2026, 7, 17, 8, 0, tzinfo=UTC)


def create_user(username: str = "dispatcher-user") -> User:
    return get_user_model().objects.create_user(username=username)


def create_reminder(user: User, *, key: str, trigger_at: datetime) -> Reminder:
    return ReminderService.create_reminder(
        CreateReminderCommand(
            user=user,
            title=f"Reminder {key}",
            trigger_at=trigger_at,
            current_time=trigger_at - timedelta(hours=1),
            timezone="Asia/Shanghai",
            deduplication_key=key,
        )
    )


def test_dispatcher_queues_only_due_pending_reminders() -> None:
    user = create_user()
    due = create_reminder(user, key="due", trigger_at=FIXED_NOW - timedelta(minutes=1))
    future = create_reminder(user, key="future", trigger_at=FIXED_NOW + timedelta(minutes=1))
    enqueued: list[UUID] = []

    count = ReminderDispatcher.dispatch_due_reminders(now=FIXED_NOW, enqueue=enqueued.append)

    due.refresh_from_db()
    future.refresh_from_db()
    assert count == 1
    assert enqueued == [due.id]
    assert due.status == ReminderStatus.QUEUED
    assert future.status == ReminderStatus.PENDING


def test_dispatcher_respects_batch_size() -> None:
    user = create_user()
    for index in range(3):
        create_reminder(
            user,
            key=f"batch-{index}",
            trigger_at=FIXED_NOW - timedelta(minutes=index + 1),
        )
    enqueued: list[UUID] = []

    count = ReminderDispatcher.dispatch_due_reminders(
        now=FIXED_NOW, enqueue=enqueued.append, batch_size=2
    )

    assert count == 2
    assert len(enqueued) == 2
    assert Reminder.objects.filter(status=ReminderStatus.QUEUED).count() == 2


def test_dispatcher_marks_stale_reminder_missed_without_enqueuing() -> None:
    user = create_user()
    stale = create_reminder(
        user,
        key="stale",
        trigger_at=FIXED_NOW - timedelta(minutes=11),
    )
    enqueued: list[UUID] = []

    count = ReminderDispatcher.dispatch_due_reminders(
        now=FIXED_NOW,
        enqueue=enqueued.append,
        max_lateness=timedelta(minutes=10),
    )

    stale.refresh_from_db()
    assert count == 0
    assert enqueued == []
    assert stale.status == ReminderStatus.MISSED
    assert not NotificationDelivery.objects.filter(source_id=stale.id).exists()


def test_send_drops_reminder_that_became_stale_after_queueing() -> None:
    reminder = create_reminder(
        create_user(),
        key="stale-in-queue",
        trigger_at=FIXED_NOW - timedelta(minutes=1),
    )
    ReminderDispatcher.dispatch_due_reminders(now=FIXED_NOW, enqueue=lambda reminder_id: None)

    sent = ReminderDispatcher.send_reminder(
        reminder.id,
        now=FIXED_NOW + timedelta(minutes=10),
        max_lateness=timedelta(minutes=10),
    )

    reminder.refresh_from_db()
    assert sent is False
    assert reminder.status == ReminderStatus.MISSED
    assert not NotificationDelivery.objects.filter(source_id=reminder.id).exists()


def test_send_hands_reminder_to_durable_deliveries_and_is_idempotent() -> None:
    reminder = create_reminder(
        create_user(), key="send-once", trigger_at=FIXED_NOW - timedelta(minutes=1)
    )
    ReminderDispatcher.dispatch_due_reminders(now=FIXED_NOW, enqueue=lambda reminder_id: None)

    first = ReminderDispatcher.send_reminder(reminder.id, now=FIXED_NOW)
    duplicate = ReminderDispatcher.send_reminder(reminder.id, now=FIXED_NOW + timedelta(seconds=1))

    reminder.refresh_from_db()
    delivery = NotificationDelivery.objects.get(source_id=reminder.id)
    assert first is True
    assert duplicate is False
    assert reminder.status == ReminderStatus.SENT
    assert delivery.channel_type == "console"
    assert delivery.status == NotificationDeliveryStatus.QUEUED


def test_delivery_creation_failure_is_recorded_and_retry_can_succeed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reminder = create_reminder(
        create_user(), key="retry", trigger_at=FIXED_NOW - timedelta(minutes=1)
    )
    ReminderDispatcher.dispatch_due_reminders(now=FIXED_NOW, enqueue=lambda reminder_id: None)

    def fail(**kwargs: object) -> list[object]:
        del kwargs
        raise OSError("database temporarily unavailable")

    monkeypatch.setattr("apps.reminders.dispatcher.create_reminder_deliveries", fail)
    with pytest.raises(ReminderDeliveryError, match="database temporarily unavailable"):
        ReminderDispatcher.send_reminder(reminder.id, now=FIXED_NOW)

    reminder.refresh_from_db()
    assert reminder.status == ReminderStatus.FAILED

    monkeypatch.undo()
    assert ReminderDispatcher.send_reminder(reminder.id, now=FIXED_NOW + timedelta(seconds=30))
    reminder.refresh_from_db()
    assert reminder.status == ReminderStatus.SENT
    assert reminder.retry_count == 1


def test_pending_reminder_cannot_be_sent_without_dispatch() -> None:
    reminder = create_reminder(
        create_user(), key="not-queued", trigger_at=FIXED_NOW - timedelta(minutes=1)
    )
    assert ReminderDispatcher.send_reminder(reminder.id, now=FIXED_NOW) is False
    reminder.refresh_from_db()
    assert reminder.status == ReminderStatus.PENDING
