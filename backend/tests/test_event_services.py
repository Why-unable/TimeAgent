from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User

from apps.events.models import CalendarEvent, CalendarEventStatus
from apps.events.services import (
    CreateEventCommand,
    EventConflictError,
    EventQuery,
    EventService,
    EventVersionConflictError,
    UpdateEventCommand,
)

pytestmark = pytest.mark.django_db

START_AT = datetime(2026, 7, 20, 1, 0, tzinfo=UTC)
END_AT = datetime(2026, 7, 20, 2, 0, tzinfo=UTC)


def create_user(username: str = "event-service-user") -> User:
    return get_user_model().objects.create_user(username=username)


def create_event(user: User, **changes: object) -> CalendarEvent:
    values: dict[str, object] = {
        "user": user,
        "title": "Project review",
        "start_at": START_AT,
        "end_at": END_AT,
        "timezone": "Asia/Shanghai",
    }
    values.update(changes)
    return EventService.create_event(CreateEventCommand(**values))  # type: ignore[arg-type]


def test_create_event_defaults_creator_and_normalizes_fields() -> None:
    user = create_user()

    event = create_event(user, title="  Project review  ")

    assert event.user == user
    assert event.created_by == user
    assert event.title == "Project review"
    assert event.version == 1


def test_update_event_increments_version_and_rejects_stale_write() -> None:
    user = create_user()
    event = create_event(user)

    updated = EventService.update_event(
        UpdateEventCommand(
            user=user,
            event_id=event.id,
            expected_version=1,
            changes={"title": "Updated review"},
        )
    )

    assert updated.title == "Updated review"
    assert updated.version == 2
    with pytest.raises(EventVersionConflictError):
        EventService.update_event(
            UpdateEventCommand(
                user=user,
                event_id=event.id,
                expected_version=1,
                changes={"title": "Stale review"},
            )
        )
    event.refresh_from_db()
    assert event.title == "Updated review"
    assert event.version == 2


def test_cancel_event_is_versioned_and_idempotent() -> None:
    user = create_user()
    event = create_event(user)

    cancelled = EventService.cancel_event(
        event_id=event.id,
        user=user,
        expected_version=1,
    )
    repeated = EventService.cancel_event(
        event_id=event.id,
        user=user,
        expected_version=2,
    )

    assert cancelled.status == CalendarEventStatus.CANCELLED
    assert cancelled.version == 2
    assert repeated.version == 2


def test_event_service_enforces_user_scope() -> None:
    owner = create_user()
    other = create_user("other-event-service-user")
    event = create_event(owner)

    with pytest.raises(CalendarEvent.DoesNotExist):
        EventService.update_event(
            UpdateEventCommand(
                user=other,
                event_id=event.id,
                expected_version=1,
                changes={"title": "Not allowed"},
            )
        )


def test_list_events_filters_by_overlap_status_and_user() -> None:
    user = create_user()
    other = create_user("event-query-other")
    matching = create_event(user)
    create_event(
        user,
        title="Earlier",
        start_at=START_AT - timedelta(hours=3),
        end_at=START_AT - timedelta(hours=2),
    )
    create_event(
        user,
        title="Cancelled",
        start_at=START_AT + timedelta(minutes=15),
        end_at=END_AT + timedelta(minutes=15),
        status=CalendarEventStatus.CANCELLED,
    )
    create_event(other, title="Other user's event")

    events = EventService.list_events(
        EventQuery(
            user=user,
            starts_before=END_AT,
            ends_after=START_AT,
            statuses=(CalendarEventStatus.CONFIRMED,),
        )
    )

    assert events == [matching]


def test_update_event_rejects_ownership_and_version_fields() -> None:
    user = create_user()
    event = create_event(user)

    with pytest.raises(ValueError, match="Unsupported event fields"):
        EventService.update_event(
            UpdateEventCommand(
                user=user,
                event_id=event.id,
                expected_version=1,
                changes={"version": 10},
            )
        )


def test_detect_conflicts_uses_half_open_intervals_and_user_scope() -> None:
    user = create_user()
    other = create_user("conflict-other")
    matching = create_event(user)
    create_event(
        user,
        title="Adjacent",
        start_at=END_AT,
        end_at=END_AT + timedelta(hours=1),
    )
    create_event(
        user,
        title="Cancelled overlap",
        start_at=START_AT + timedelta(minutes=15),
        end_at=END_AT,
        status=CalendarEventStatus.CANCELLED,
    )
    create_event(other, title="Other user's overlap")

    conflicts = EventService.detect_conflicts(
        user=user,
        start_at=START_AT + timedelta(minutes=30),
        end_at=END_AT,
    )

    assert conflicts == [matching]
    assert (
        EventService.detect_conflicts(
            user=user,
            start_at=START_AT,
            end_at=END_AT,
            exclude_event_id=matching.id,
        )
        == []
    )


def test_detect_conflicts_rejects_invalid_range() -> None:
    user = create_user()

    with pytest.raises(ValueError, match="later than"):
        EventService.detect_conflicts(user=user, start_at=START_AT, end_at=START_AT)


def test_event_service_blocks_overlapping_create_and_update() -> None:
    user = create_user()
    existing = create_event(user)

    with pytest.raises(EventConflictError) as create_error:
        create_event(
            user,
            title="Overlapping review",
            start_at=START_AT + timedelta(minutes=30),
            end_at=END_AT + timedelta(minutes=30),
        )
    assert create_error.value.preview.conflicts[0].event_id == existing.id

    later = create_event(
        user,
        title="Later review",
        start_at=END_AT + timedelta(hours=1),
        end_at=END_AT + timedelta(hours=2),
    )
    with pytest.raises(EventConflictError):
        EventService.update_event(
            UpdateEventCommand(
                user=user,
                event_id=later.id,
                expected_version=later.version,
                changes={"start_at": START_AT + timedelta(minutes=30), "end_at": END_AT},
            )
        )
    later.refresh_from_db()
    assert later.start_at == END_AT + timedelta(hours=1)


def test_event_batch_is_atomic_when_one_item_conflicts() -> None:
    user = create_user()
    existing = create_event(user)

    with pytest.raises(EventConflictError):
        EventService.create_events(
            commands=[
                CreateEventCommand(
                    user=user,
                    title="Safe first item",
                    start_at=END_AT + timedelta(hours=2),
                    end_at=END_AT + timedelta(hours=3),
                    timezone="Asia/Shanghai",
                ),
                CreateEventCommand(
                    user=user,
                    title="Conflicting second item",
                    start_at=START_AT + timedelta(minutes=30),
                    end_at=END_AT + timedelta(minutes=30),
                    timezone="Asia/Shanghai",
                ),
            ]
        )
    assert list(CalendarEvent.objects.all()) == [existing]
