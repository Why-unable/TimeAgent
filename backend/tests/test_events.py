from datetime import UTC, datetime

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.events.models import (
    CalendarEvent,
    CalendarEventStatus,
    CalendarEventVisibility,
)

pytestmark = pytest.mark.django_db

START_AT = datetime(2026, 7, 20, 1, 0, tzinfo=UTC)
END_AT = datetime(2026, 7, 20, 2, 0, tzinfo=UTC)


def create_user(username: str = "event-user") -> User:
    return get_user_model().objects.create_user(username=username)


def build_event(user: User, **changes: object) -> CalendarEvent:
    values: dict[str, object] = {
        "user": user,
        "created_by": user,
        "title": "Project review",
        "start_at": START_AT,
        "end_at": END_AT,
        "timezone": "Asia/Shanghai",
    }
    values.update(changes)
    return CalendarEvent(**values)


def test_calendar_event_defaults_and_utc_storage() -> None:
    event = build_event(create_user(), title="  Project review  ")

    event.full_clean()
    event.save()
    event.refresh_from_db()

    assert event.title == "Project review"
    assert event.start_at == START_AT
    assert event.end_at == END_AT
    assert event.status == CalendarEventStatus.CONFIRMED
    assert event.visibility == CalendarEventVisibility.PRIVATE
    assert event.source == "local"
    assert event.version == 1


def test_calendar_event_requires_aware_times_and_iana_timezone() -> None:
    event = build_event(
        create_user(),
        start_at=datetime(2026, 7, 20, 9, 0),
        end_at=datetime(2026, 7, 20, 10, 0),
        timezone="UTC+8",
    )

    with pytest.raises(ValidationError) as error:
        event.full_clean()

    assert "start_at" in error.value.message_dict
    assert "end_at" in error.value.message_dict
    assert "timezone" in error.value.message_dict


def test_calendar_event_end_must_be_after_start() -> None:
    event = build_event(create_user(), end_at=START_AT)

    with pytest.raises(ValidationError) as error:
        event.full_clean()

    assert "end_at" in error.value.message_dict


def test_external_identity_must_match_source() -> None:
    local_event = build_event(create_user(), external_id="external-123")
    external_event = build_event(create_user("external-event-user"), source="google")

    with pytest.raises(ValidationError) as local_error:
        local_event.full_clean()
    with pytest.raises(ValidationError) as external_error:
        external_event.full_clean()

    assert "external_id" in local_error.value.message_dict
    assert "external_id" in external_error.value.message_dict


def test_external_identity_is_unique_per_user_and_source() -> None:
    user = create_user()
    first = build_event(user, source="google", external_id="google-event-123")
    duplicate = build_event(
        user,
        title="Duplicate external event",
        source="google",
        external_id="google-event-123",
    )
    first.full_clean()
    first.save()

    with pytest.raises(ValidationError):
        duplicate.full_clean()
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            duplicate.save()


def test_overlapping_events_are_allowed_at_model_layer() -> None:
    user = create_user()
    first = build_event(user)
    overlapping = build_event(
        user,
        title="Overlapping review",
        start_at=datetime(2026, 7, 20, 1, 30, tzinfo=UTC),
        end_at=datetime(2026, 7, 20, 2, 30, tzinfo=UTC),
    )

    first.full_clean()
    first.save()
    overlapping.full_clean()
    overlapping.save()

    assert CalendarEvent.objects.count() == 2


def test_deleting_owner_cascades_event_without_created_by_blocking() -> None:
    user = create_user()
    event = build_event(user)
    event.full_clean()
    event.save()

    user.delete()

    assert not CalendarEvent.objects.filter(pk=event.pk).exists()
