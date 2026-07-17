from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User

from apps.reminders.dispatcher import ReminderDeliveryError, ReminderDispatcher
from apps.reminders.models import Reminder, ReminderStatus
from apps.reminders.providers import (
    ConsoleNotificationProvider,
    DeliveryResult,
)
from apps.reminders.services import CreateReminderCommand, ReminderService

pytestmark = pytest.mark.django_db

FIXED_NOW = datetime(2026, 7, 17, 8, 0, tzinfo=UTC)


class RecordingProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def send(
        self,
        *,
        recipient: str,
        title: str,
        content: str,
        idempotency_key: str,
    ) -> DeliveryResult:
        self.calls.append(
            {
                "recipient": recipient,
                "title": title,
                "content": content,
                "idempotency_key": idempotency_key,
            }
        )
        return DeliveryResult(delivered=True, provider_message_id=idempotency_key)


class FailingProvider:
    def send(
        self,
        *,
        recipient: str,
        title: str,
        content: str,
        idempotency_key: str,
    ) -> DeliveryResult:
        del recipient, title, content, idempotency_key
        raise OSError("console unavailable")


def create_user(username: str = "dispatcher-user") -> User:
    return get_user_model().objects.create_user(username=username)


def create_reminder(
    user: User,
    *,
    key: str,
    trigger_at: datetime,
) -> Reminder:
    return ReminderService.create_reminder(
        CreateReminderCommand(
            user=user,
            title=f"Reminder {key}",
            trigger_at=trigger_at,
            timezone="Asia/Shanghai",
            deduplication_key=key,
        )
    )


def test_dispatcher_queues_only_due_pending_reminders() -> None:
    user = create_user()
    due = create_reminder(
        user,
        key="due",
        trigger_at=FIXED_NOW - timedelta(minutes=1),
    )
    future = create_reminder(
        user,
        key="future",
        trigger_at=FIXED_NOW + timedelta(minutes=1),
    )
    enqueued: list[UUID] = []

    count = ReminderDispatcher.dispatch_due_reminders(
        now=FIXED_NOW,
        enqueue=enqueued.append,
    )

    due.refresh_from_db()
    future.refresh_from_db()
    assert count == 1
    assert enqueued == [due.id]
    assert due.status == ReminderStatus.QUEUED
    assert due.queued_at == FIXED_NOW
    assert future.status == ReminderStatus.PENDING


def test_dispatcher_respects_batch_size() -> None:
    user = create_user()
    reminders = [
        create_reminder(
            user,
            key=f"batch-{index}",
            trigger_at=FIXED_NOW - timedelta(minutes=index + 1),
        )
        for index in range(3)
    ]
    enqueued: list[UUID] = []

    count = ReminderDispatcher.dispatch_due_reminders(
        now=FIXED_NOW,
        enqueue=enqueued.append,
        batch_size=2,
    )

    assert count == 2
    assert len(enqueued) == 2
    assert Reminder.objects.filter(status=ReminderStatus.QUEUED).count() == 2
    assert Reminder.objects.filter(status=ReminderStatus.PENDING).count() == 1
    assert {reminder.id for reminder in reminders}.issuperset(enqueued)


def test_send_marks_reminder_sent_and_is_idempotent() -> None:
    reminder = create_reminder(
        create_user(),
        key="send-once",
        trigger_at=FIXED_NOW - timedelta(minutes=1),
    )
    ReminderDispatcher.dispatch_due_reminders(
        now=FIXED_NOW,
        enqueue=lambda reminder_id: None,
    )
    provider = RecordingProvider()

    first_result = ReminderDispatcher.send_reminder(
        reminder.id,
        now=FIXED_NOW,
        provider=provider,
    )
    duplicate_result = ReminderDispatcher.send_reminder(
        reminder.id,
        now=FIXED_NOW + timedelta(seconds=1),
        provider=provider,
    )

    reminder.refresh_from_db()
    assert first_result is True
    assert duplicate_result is False
    assert reminder.status == ReminderStatus.SENT
    assert reminder.sent_at == FIXED_NOW
    assert len(provider.calls) == 1
    assert provider.calls[0]["idempotency_key"] == f"reminder:{reminder.id}"


def test_provider_failure_is_recorded_and_retry_can_succeed() -> None:
    reminder = create_reminder(
        create_user(),
        key="retry",
        trigger_at=FIXED_NOW - timedelta(minutes=1),
    )
    ReminderDispatcher.dispatch_due_reminders(
        now=FIXED_NOW,
        enqueue=lambda reminder_id: None,
    )

    with pytest.raises(ReminderDeliveryError, match="console unavailable"):
        ReminderDispatcher.send_reminder(
            reminder.id,
            now=FIXED_NOW,
            provider=FailingProvider(),
        )

    reminder.refresh_from_db()
    assert reminder.status == ReminderStatus.FAILED
    assert reminder.failure_reason == "console unavailable"

    delivered = ReminderDispatcher.send_reminder(
        reminder.id,
        now=FIXED_NOW + timedelta(seconds=30),
        provider=RecordingProvider(),
    )

    reminder.refresh_from_db()
    assert delivered is True
    assert reminder.status == ReminderStatus.SENT
    assert reminder.retry_count == 1
    assert reminder.failure_reason == ""


def test_pending_reminder_cannot_be_sent_without_dispatch() -> None:
    reminder = create_reminder(
        create_user(),
        key="not-queued",
        trigger_at=FIXED_NOW - timedelta(minutes=1),
    )
    provider = RecordingProvider()

    result = ReminderDispatcher.send_reminder(
        reminder.id,
        now=FIXED_NOW,
        provider=provider,
    )

    reminder.refresh_from_db()
    assert result is False
    assert reminder.status == ReminderStatus.PENDING
    assert provider.calls == []


@pytest.mark.django_db(transaction=True)
def test_console_provider_returns_stable_delivery_result(caplog: pytest.LogCaptureFixture) -> None:
    provider = ConsoleNotificationProvider()

    with caplog.at_level("INFO"):
        result = provider.send(
            recipient="42",
            title="Submit report",
            content="Submit report",
            idempotency_key="reminder:fixed-id",
        )

    assert result.delivered is True
    assert result.provider_message_id == "reminder:fixed-id"
    assert "Reminder delivered to console" in caplog.text
