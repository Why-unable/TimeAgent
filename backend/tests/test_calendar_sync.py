from datetime import UTC, datetime
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.test import Client

from apps.events.models import CalendarEvent, CalendarEventStatus
from apps.integrations.calendar.capabilities import CalendarProviderCapabilities
from apps.integrations.calendar.dto import (
    ExternalCalendarContext,
    ExternalCalendarSummary,
    ExternalEvent,
    ExternalEventPage,
    ExternalEventQuery,
    ExternalEventTombstone,
)
from apps.integrations.calendar.sync_services import (
    CalendarSyncService,
    SyncExternalCalendarCommand,
)
from apps.integrations.models import CalendarSyncConnection

pytestmark = pytest.mark.django_db

START = datetime(2026, 8, 24, 1, 0, tzinfo=UTC)
END = datetime(2026, 8, 24, 3, 0, tzinfo=UTC)


class FakeCalendarProvider:
    provider_name = "fake-calendar"

    def __init__(
        self,
        events: list[ExternalEvent | ExternalEventTombstone],
        *,
        next_sync_cursor: str = "",
        cursor_was_reset: bool = False,
    ) -> None:
        self.events = events
        self.next_sync_cursor = next_sync_cursor
        self.cursor_was_reset = cursor_was_reset
        self.last_query: ExternalEventQuery | None = None

    def get_capabilities(self) -> CalendarProviderCapabilities:
        return CalendarProviderCapabilities(read_calendars=True, read_events=True)

    def list_calendars(self, context: ExternalCalendarContext) -> list[ExternalCalendarSummary]:
        return [
            ExternalCalendarSummary(
                external_id="calendar-1",
                name="Primary",
                timezone=context.timezone,
            )
        ]

    def list_events(
        self,
        context: ExternalCalendarContext,
        query: ExternalEventQuery,
    ) -> ExternalEventPage:
        del context
        self.last_query = query
        return ExternalEventPage(
            events=tuple(self.events),
            next_sync_cursor=self.next_sync_cursor,
            cursor_was_reset=self.cursor_was_reset,
        )

    def create_event(self, context: ExternalCalendarContext, event: Any) -> ExternalEvent:
        raise AssertionError("read-only sync must not create external events")

    def update_event(
        self,
        context: ExternalCalendarContext,
        external_event_id: str,
        event: Any,
    ) -> ExternalEvent:
        raise AssertionError("read-only sync must not update external events")

    def cancel_event(self, context: ExternalCalendarContext, external_event_id: str) -> None:
        raise AssertionError("read-only sync must not cancel external events")


class FailingCalendarProvider(FakeCalendarProvider):
    def list_events(
        self,
        context: ExternalCalendarContext,
        query: ExternalEventQuery,
    ) -> ExternalEventPage:
        del context, query
        raise RuntimeError("provider unavailable")


def create_user(username: str = "calendar-sync-user") -> User:
    return get_user_model().objects.create_user(username=username)


def create_connection(user: User) -> CalendarSyncConnection:
    return CalendarSyncConnection.objects.create(
        user=user,
        provider_name="fake-calendar",
        account_reference="account-1",
        calendar_id="calendar-1",
        calendar_name="Primary",
        timezone="Asia/Shanghai",
    )


def external_event(status: str = "confirmed", title: str = "External meeting") -> ExternalEvent:
    return ExternalEvent(
        external_id="event-1",
        calendar_id="calendar-1",
        title=title,
        starts_at=START,
        ends_at=END,
        timezone="Asia/Shanghai",
        status=status,
    )


def test_read_only_calendar_sync_upserts_and_cancels_local_facts() -> None:
    user = create_user()
    connection = create_connection(user)
    provider = FakeCalendarProvider([external_event()])

    result = CalendarSyncService.sync(
        SyncExternalCalendarCommand(
            user=user,
            connection_id=connection.pk,
            provider=provider,
            starts_at_or_after=START,
            starts_before=END,
        )
    )

    event = CalendarEvent.objects.get(user=user, source="fake-calendar", external_id="event-1")
    assert result.created_count == 1
    assert result.updated_count == 0
    assert event.title == "External meeting"
    assert provider.last_query is not None
    assert provider.last_query.starts_at_or_after == START

    provider.events = [external_event(status="cancelled", title="Cancelled meeting")]
    second = CalendarSyncService.sync(
        SyncExternalCalendarCommand(
            user=user,
            connection_id=connection.pk,
            provider=provider,
            starts_at_or_after=START,
            starts_before=END,
        )
    )
    event.refresh_from_db()
    connection.refresh_from_db()
    assert second.updated_count == 1
    assert second.cancelled_count == 1
    assert event.status == CalendarEventStatus.CANCELLED
    assert connection.last_synced_at is not None
    assert connection.sync_cursor.endswith("+00:00")


def test_calendar_sync_connection_status_is_user_scoped() -> None:
    owner = create_user("calendar-status-owner")
    other = create_user("calendar-status-other")
    create_connection(owner)
    client = Client()
    client.force_login(owner)
    other_client = Client()
    other_client.force_login(other)

    response = client.get("/api/v1/integrations/calendar/connections/")
    hidden = other_client.get("/api/v1/integrations/calendar/connections/")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert hidden.status_code == 200
    assert hidden.json() == []


def test_calendar_sync_records_provider_failure_on_connection() -> None:
    user = create_user("calendar-sync-error")
    connection = create_connection(user)

    with pytest.raises(RuntimeError, match="provider unavailable"):
        CalendarSyncService.sync(
            SyncExternalCalendarCommand(
                user=user,
                connection_id=connection.pk,
                provider=FailingCalendarProvider([]),
                starts_at_or_after=START,
                starts_before=END,
            )
        )

    connection.refresh_from_db()
    assert connection.status == "error"
    assert connection.last_error == "Calendar provider sync failed"


def test_calendar_sync_persists_provider_cursor_and_applies_tombstone() -> None:
    user = create_user("calendar-sync-tombstone")
    connection = create_connection(user)
    CalendarSyncService.sync(
        SyncExternalCalendarCommand(
            user=user,
            connection_id=connection.pk,
            provider=FakeCalendarProvider([external_event()], next_sync_cursor="cursor-1"),
            starts_at_or_after=START,
            starts_before=END,
        )
    )
    connection.refresh_from_db()
    assert connection.sync_cursor == "cursor-1"

    provider = FakeCalendarProvider(
        [ExternalEventTombstone(external_id="event-1", calendar_id="calendar-1")],
        next_sync_cursor="cursor-2",
    )
    result = CalendarSyncService.sync(
        SyncExternalCalendarCommand(
            user=user,
            connection_id=connection.pk,
            provider=provider,
            starts_at_or_after=START,
            starts_before=END,
        )
    )

    event = CalendarEvent.objects.get(user=user, source="fake-calendar", external_id="event-1")
    connection.refresh_from_db()
    assert provider.last_query is not None
    assert provider.last_query.sync_cursor == "cursor-1"
    assert result.fetched_count == 1
    assert result.updated_count == 1
    assert result.cancelled_count == 1
    assert event.status == CalendarEventStatus.CANCELLED
    assert connection.sync_cursor == "cursor-2"


def test_calendar_sync_scopes_same_provider_event_id_to_account_and_calendar() -> None:
    user = create_user("calendar-sync-identity")
    first_connection = create_connection(user)
    second_connection = CalendarSyncConnection.objects.create(
        user=user,
        provider_name="fake-calendar",
        account_reference="account-2",
        calendar_id="calendar-2",
        calendar_name="Secondary",
        timezone="Asia/Shanghai",
    )
    CalendarSyncService.sync(
        SyncExternalCalendarCommand(
            user=user,
            connection_id=first_connection.pk,
            provider=FakeCalendarProvider([external_event(title="First calendar")]),
            starts_at_or_after=START,
            starts_before=END,
        )
    )
    CalendarSyncService.sync(
        SyncExternalCalendarCommand(
            user=user,
            connection_id=second_connection.pk,
            provider=FakeCalendarProvider(
                [
                    external_event(title="Second calendar").model_copy(
                        update={"calendar_id": "calendar-2"}
                    )
                ]
            ),
            starts_at_or_after=START,
            starts_before=END,
        )
    )

    events = CalendarEvent.objects.filter(
        user=user,
        source="fake-calendar",
        external_id="event-1",
    ).order_by("external_calendar_id")
    assert list(events.values_list("title", flat=True)) == [
        "First calendar",
        "Second calendar",
    ]

    CalendarSyncService.sync(
        SyncExternalCalendarCommand(
            user=user,
            connection_id=first_connection.pk,
            provider=FakeCalendarProvider(
                [ExternalEventTombstone(external_id="event-1", calendar_id="calendar-1")]
            ),
            starts_at_or_after=START,
            starts_before=END,
        )
    )

    assert events.get(external_calendar_id="calendar-1").status == CalendarEventStatus.CANCELLED
    assert events.get(external_calendar_id="calendar-2").status == CalendarEventStatus.CONFIRMED


def test_calendar_sync_reconciles_missing_events_after_cursor_reset_within_range() -> None:
    user = create_user("calendar-sync-reset")
    connection = create_connection(user)
    CalendarSyncService.sync(
        SyncExternalCalendarCommand(
            user=user,
            connection_id=connection.pk,
            provider=FakeCalendarProvider([external_event()], next_sync_cursor="old-cursor"),
            starts_at_or_after=START,
            starts_before=END,
        )
    )
    outside = CalendarEvent(
        user=user,
        created_by=user,
        title="Outside reset window",
        start_at=datetime(2026, 8, 27, 1, 0, tzinfo=UTC),
        end_at=datetime(2026, 8, 27, 2, 0, tzinfo=UTC),
        timezone="Asia/Shanghai",
        source="fake-calendar",
        external_account_reference="account-1",
        external_calendar_id="calendar-1",
        external_id="outside-event",
    )
    outside.full_clean()
    outside.save()

    result = CalendarSyncService.sync(
        SyncExternalCalendarCommand(
            user=user,
            connection_id=connection.pk,
            provider=FakeCalendarProvider(
                [],
                next_sync_cursor="replacement-cursor",
                cursor_was_reset=True,
            ),
            starts_at_or_after=START,
            starts_before=END,
        )
    )

    event = CalendarEvent.objects.get(user=user, external_id="event-1")
    outside.refresh_from_db()
    connection.refresh_from_db()
    assert result.fetched_count == 0
    assert result.updated_count == 1
    assert result.cancelled_count == 1
    assert event.status == CalendarEventStatus.CANCELLED
    assert outside.status == CalendarEventStatus.CONFIRMED
    assert connection.sync_cursor == "replacement-cursor"


def test_calendar_connection_api_can_register_read_only_ics_feed() -> None:
    user = create_user("calendar-api")
    client = Client()
    client.force_login(user)
    response = client.post(
        "/api/v1/integrations/calendar/connections/",
        data={
            "provider_name": "ics",
            "account_reference": "https://calendar.example/feed.ics",
            "calendar_id": "https://calendar.example/feed.ics",
            "calendar_name": "Personal",
            "timezone": "Asia/Shanghai",
            "enabled": True,
        },
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json()["provider_name"] == "ics"
