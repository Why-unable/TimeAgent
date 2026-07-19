import uuid
from datetime import UTC, datetime

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client

from apps.reminders.models import (
    InvalidReminderTransitionError,
    Reminder,
    ReminderChannel,
    ReminderStatus,
    ReminderTargetType,
)
from apps.reminders.services import (
    CreateReminderCommand,
    ReminderIdempotencyConflictError,
    ReminderService,
)

pytestmark = pytest.mark.django_db

FIXED_NOW = datetime(2026, 7, 17, 2, 0, tzinfo=UTC)
FIXED_TRIGGER = datetime(2026, 7, 17, 7, 0, tzinfo=UTC)


def create_user(username: str = "reminder-user") -> User:
    return get_user_model().objects.create_user(username=username)


def build_reminder(user: User, **changes: object) -> Reminder:
    values: dict[str, object] = {
        "user": user,
        "title": "Submit report",
        "trigger_at": FIXED_TRIGGER,
        "timezone": "Asia/Shanghai",
        "deduplication_key": "submit-report-2026-07-17",
    }
    values.update(changes)
    return Reminder(**values)


def test_reminder_defaults_and_utc_storage() -> None:
    reminder = build_reminder(create_user())

    reminder.full_clean()
    reminder.save()
    reminder.refresh_from_db()

    assert reminder.status == ReminderStatus.PENDING
    assert reminder.trigger_at == FIXED_TRIGGER
    assert reminder.retry_count == 0
    assert reminder.target_type == ReminderTargetType.CUSTOM


def test_reminder_requires_iana_timezone_and_aware_trigger() -> None:
    reminder = build_reminder(
        create_user(),
        timezone="UTC+8",
        trigger_at=datetime(2026, 7, 17, 15, 0),
    )

    with pytest.raises(ValidationError) as error:
        reminder.full_clean()

    assert "timezone" in error.value.message_dict
    assert "trigger_at" in error.value.message_dict


def test_target_reference_must_match_target_type() -> None:
    custom_reminder = build_reminder(create_user(), target_id=uuid.uuid4())
    event_reminder = build_reminder(
        create_user("event-user"),
        target_type=ReminderTargetType.CALENDAR_EVENT,
        target_id=None,
    )

    with pytest.raises(ValidationError) as custom_error:
        custom_reminder.full_clean()
    with pytest.raises(ValidationError) as event_error:
        event_reminder.full_clean()

    assert "target_id" in custom_error.value.message_dict
    assert "target_id" in event_error.value.message_dict


def test_deduplication_key_is_unique_per_user() -> None:
    user = create_user()
    first = build_reminder(user)
    first.full_clean()
    first.save()
    duplicate = build_reminder(user, title="Duplicate")

    with pytest.raises(ValidationError) as validation_error:
        duplicate.full_clean()

    assert "__all__" in validation_error.value.message_dict

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            duplicate.save()


def test_same_deduplication_key_is_allowed_for_different_users() -> None:
    first = build_reminder(create_user("first-user"))
    second = build_reminder(create_user("second-user"))

    first.full_clean()
    first.save()
    second.full_clean()
    second.save()

    assert Reminder.objects.count() == 2


def test_service_creates_validated_reminder() -> None:
    user = create_user()

    reminder = ReminderService.create_reminder(
        CreateReminderCommand(
            user=user,
            title="  Submit report  ",
            trigger_at=FIXED_TRIGGER,
            timezone="Asia/Shanghai",
            deduplication_key="  submit-report-service  ",
        )
    )

    assert reminder.title == "Submit report"
    assert reminder.deduplication_key == "submit-report-service"
    assert reminder.channel == ReminderChannel.CONSOLE
    assert reminder.status == ReminderStatus.PENDING
    assert Reminder.objects.filter(pk=reminder.pk).exists()


def test_service_returns_existing_reminder_for_idempotent_retry() -> None:
    user = create_user()
    command = CreateReminderCommand(
        user=user,
        title="Submit report",
        trigger_at=FIXED_TRIGGER,
        timezone="Asia/Shanghai",
        deduplication_key="service-idempotency-key",
    )

    first = ReminderService.create_reminder(command)
    second = ReminderService.create_reminder(command)

    assert second.pk == first.pk
    assert Reminder.objects.filter(user=user).count() == 1


def test_service_rejects_reused_key_with_different_payload() -> None:
    user = create_user()
    ReminderService.create_reminder(
        CreateReminderCommand(
            user=user,
            title="Submit report",
            trigger_at=FIXED_TRIGGER,
            timezone="Asia/Shanghai",
            deduplication_key="conflicting-service-key",
        )
    )

    with pytest.raises(
        ReminderIdempotencyConflictError,
        match="different reminder data: title",
    ):
        ReminderService.create_reminder(
            CreateReminderCommand(
                user=user,
                title="Submit another report",
                trigger_at=FIXED_TRIGGER,
                timezone="Asia/Shanghai",
                deduplication_key="conflicting-service-key",
            )
        )

    assert Reminder.objects.filter(user=user).count() == 1


def test_service_scopes_idempotency_key_to_user() -> None:
    first = ReminderService.create_reminder(
        CreateReminderCommand(
            user=create_user("service-first-user"),
            title="Submit report",
            trigger_at=FIXED_TRIGGER,
            timezone="Asia/Shanghai",
            deduplication_key="shared-service-key",
        )
    )
    second = ReminderService.create_reminder(
        CreateReminderCommand(
            user=create_user("service-second-user"),
            title="Submit report",
            trigger_at=FIXED_TRIGGER,
            timezone="Asia/Shanghai",
            deduplication_key="shared-service-key",
        )
    )

    assert first.pk != second.pk
    assert Reminder.objects.count() == 2


def test_service_rejects_invalid_command_before_writing() -> None:
    user = create_user()

    with pytest.raises(ValidationError):
        ReminderService.create_reminder(
            CreateReminderCommand(
                user=user,
                title="Submit report",
                trigger_at=datetime(2026, 7, 17, 15, 0),
                timezone="UTC+8",
                deduplication_key="invalid-service-command",
            )
        )

    assert not Reminder.objects.filter(user=user).exists()


def test_service_cancels_pending_reminder_idempotently() -> None:
    user = create_user()
    reminder = ReminderService.create_reminder(
        CreateReminderCommand(
            user=user,
            title="Cancel me",
            trigger_at=FIXED_TRIGGER,
            timezone="Asia/Shanghai",
            deduplication_key="cancel-reminder-service",
        )
    )

    cancelled = ReminderService.cancel_reminder(
        reminder_id=reminder.pk,
        user=user,
        occurred_at=FIXED_NOW,
    )
    repeated = ReminderService.cancel_reminder(
        reminder_id=reminder.pk,
        user=user,
        occurred_at=FIXED_NOW,
    )

    assert cancelled.status == ReminderStatus.CANCELLED
    assert repeated.pk == reminder.pk
    assert Reminder.objects.filter(pk=reminder.pk, status=ReminderStatus.CANCELLED).exists()


def test_successful_state_transition_sequence() -> None:
    reminder = build_reminder(create_user())

    reminder.transition_to(ReminderStatus.QUEUED, occurred_at=FIXED_NOW)
    reminder.transition_to(
        ReminderStatus.SENDING,
        occurred_at=datetime(2026, 7, 17, 2, 1, tzinfo=UTC),
    )
    reminder.transition_to(
        ReminderStatus.SENT,
        occurred_at=datetime(2026, 7, 17, 2, 2, tzinfo=UTC),
    )

    assert reminder.status == ReminderStatus.SENT
    assert reminder.queued_at == FIXED_NOW
    assert reminder.sent_at == datetime(2026, 7, 17, 2, 2, tzinfo=UTC)
    assert not reminder.can_transition_to(ReminderStatus.FAILED)


def test_failed_reminder_can_be_requeued_and_counts_retry() -> None:
    reminder = build_reminder(create_user())
    reminder.transition_to(ReminderStatus.QUEUED, occurred_at=FIXED_NOW)
    reminder.transition_to(
        ReminderStatus.FAILED,
        occurred_at=datetime(2026, 7, 17, 2, 1, tzinfo=UTC),
        failure_reason="Notification provider unavailable",
    )
    reminder.transition_to(
        ReminderStatus.QUEUED,
        occurred_at=datetime(2026, 7, 17, 2, 5, tzinfo=UTC),
    )

    assert reminder.status == ReminderStatus.QUEUED
    assert reminder.retry_count == 1
    assert reminder.failure_reason == ""
    assert reminder.queued_at == datetime(2026, 7, 17, 2, 5, tzinfo=UTC)


def test_invalid_transitions_and_missing_failure_reason_are_rejected() -> None:
    reminder = build_reminder(create_user())

    with pytest.raises(InvalidReminderTransitionError, match="Cannot transition"):
        reminder.transition_to(ReminderStatus.SENT, occurred_at=FIXED_NOW)

    reminder.transition_to(ReminderStatus.QUEUED, occurred_at=FIXED_NOW)
    with pytest.raises(InvalidReminderTransitionError, match="failure reason"):
        reminder.transition_to(
            ReminderStatus.FAILED,
            occurred_at=datetime(2026, 7, 17, 2, 1, tzinfo=UTC),
        )


def test_cancelled_and_sent_reminders_are_terminal() -> None:
    cancelled = build_reminder(create_user("cancelled-user"))
    cancelled.transition_to(ReminderStatus.CANCELLED, occurred_at=FIXED_NOW)

    sent = build_reminder(create_user("sent-user"), deduplication_key="sent-key")
    sent.transition_to(ReminderStatus.QUEUED, occurred_at=FIXED_NOW)
    sent.transition_to(
        ReminderStatus.SENDING,
        occurred_at=datetime(2026, 7, 17, 2, 1, tzinfo=UTC),
    )
    sent.transition_to(
        ReminderStatus.SENT,
        occurred_at=datetime(2026, 7, 17, 2, 2, tzinfo=UTC),
    )

    assert not cancelled.can_transition_to(ReminderStatus.PENDING)
    assert not sent.can_transition_to(ReminderStatus.QUEUED)


def test_reminder_api_requires_authentication() -> None:
    response = Client().get("/api/v1/reminders/")

    assert response.status_code in (401, 403)


def test_reminder_api_lists_only_current_users_reminders() -> None:
    user = create_user()
    own = build_reminder(user, deduplication_key="own-reminder")
    own.full_clean()
    own.save()
    other = build_reminder(
        create_user("other-api-user"),
        deduplication_key="other-reminder",
    )
    other.full_clean()
    other.save()
    client = Client()
    client.force_login(user)

    response = client.get("/api/v1/reminders/")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(own.id)]


def test_reminder_api_creates_via_service_and_retries_idempotently() -> None:
    user = create_user()
    client = Client()
    client.force_login(user)
    payload = {
        "title": "Submit API report",
        "trigger_at": "2026-07-17T15:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "channel": "console",
        "deduplication_key": "api-create-reminder",
    }

    first = client.post(
        "/api/v1/reminders/",
        data=payload,
        content_type="application/json",
    )
    retried = client.post(
        "/api/v1/reminders/",
        data=payload,
        content_type="application/json",
    )

    assert first.status_code == 201
    assert retried.status_code == 201
    assert retried.json()["id"] == first.json()["id"]
    assert first.json()["trigger_at"] == "2026-07-17T07:00:00Z"
    assert Reminder.objects.filter(user=user).count() == 1


def test_reminder_api_rejects_datetime_without_explicit_offset() -> None:
    user = create_user()
    client = Client()
    client.force_login(user)

    response = client.post(
        "/api/v1/reminders/",
        data={
            "title": "Ambiguous reminder",
            "trigger_at": "2026-07-17T15:00:00",
            "timezone": "Asia/Shanghai",
            "deduplication_key": "ambiguous-api-reminder",
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "trigger_at" in response.json()


def test_reminder_api_cancels_without_deleting() -> None:
    user = create_user()
    reminder = build_reminder(user, deduplication_key="cancel-via-api")
    reminder.full_clean()
    reminder.save()
    client = Client()
    client.force_login(user)

    first = client.delete(f"/api/v1/reminders/{reminder.id}/")
    retried = client.delete(f"/api/v1/reminders/{reminder.id}/")

    reminder.refresh_from_db()
    assert first.status_code == 204
    assert retried.status_code == 204
    assert reminder.status == ReminderStatus.CANCELLED


def test_reminder_api_hides_other_users_reminders() -> None:
    owner = create_user("api-owner")
    reminder = build_reminder(owner, deduplication_key="private-api-reminder")
    reminder.full_clean()
    reminder.save()
    client = Client()
    client.force_login(create_user("api-attacker"))

    response = client.delete(f"/api/v1/reminders/{reminder.id}/")

    reminder.refresh_from_db()
    assert response.status_code == 404
    assert reminder.status == ReminderStatus.PENDING


def test_reminder_api_returns_conflict_when_sent_reminder_cannot_be_cancelled() -> None:
    user = create_user()
    reminder = build_reminder(user, deduplication_key="sent-api-reminder")
    reminder.transition_to(ReminderStatus.QUEUED, occurred_at=FIXED_NOW)
    reminder.transition_to(ReminderStatus.SENDING, occurred_at=FIXED_NOW)
    reminder.transition_to(ReminderStatus.SENT, occurred_at=FIXED_NOW)
    reminder.full_clean()
    reminder.save()
    client = Client()
    client.force_login(user)

    response = client.delete(f"/api/v1/reminders/{reminder.id}/")

    assert response.status_code == 409
    assert "cannot be cancelled" in response.json()["detail"]
