from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.test import override_settings

from apps.integrations.calendar.capabilities import CalendarProviderCapabilities
from apps.integrations.calendar.dto import ExternalEventPage
from apps.integrations.calendar.polling import CalendarPollingService, CalendarProviderFactory
from apps.integrations.calendar.sync_services import CalendarSyncService
from apps.integrations.models import CalendarSyncConnection
from apps.integrations.tasks import dispatch_calendar_polls

pytestmark = pytest.mark.django_db
NOW = datetime(2026, 8, 24, 8, tzinfo=UTC)


class EmptyCalendarProvider:
    def __init__(self) -> None:
        self.query: Any = None

    def get_capabilities(self) -> CalendarProviderCapabilities:
        return CalendarProviderCapabilities(read_events=True)

    def list_events(self, context: Any, query: Any) -> ExternalEventPage:
        del context
        self.query = query
        return ExternalEventPage(events=(), next_sync_cursor="poll-cursor")


def create_connection(user: User, *, enabled: bool = True) -> CalendarSyncConnection:
    feed_url = f"https://calendar.example.test/{uuid4()}.ics"
    return CalendarSyncService.create_connection(
        user=user,
        provider_name="ics",
        account_reference=feed_url,
        calendar_id=feed_url,
        calendar_name="Read-only calendar",
        timezone_name="Asia/Shanghai",
        enabled=enabled,
    )


def make_due(connection: CalendarSyncConnection, *, minutes: int = 10) -> None:
    CalendarSyncConnection.objects.filter(pk=connection.pk).update(
        updated_at=NOW - timedelta(minutes=minutes)
    )


def test_polling_selects_only_due_enabled_connections_in_stable_order() -> None:
    user = User.objects.create_user("poll-candidates")
    first = create_connection(user)
    second = create_connection(user)
    disabled = create_connection(user, enabled=False)
    make_due(first, minutes=12)
    make_due(second, minutes=10)
    make_due(disabled)

    ids = CalendarPollingService.list_due_connection_ids(
        now=NOW,
        minimum_interval=timedelta(minutes=5),
        batch_size=1,
    )

    assert ids == [first.pk]


def test_polling_sync_uses_bounded_window_and_existing_sync_service() -> None:
    user = User.objects.create_user("poll-sync")
    connection = create_connection(user)
    provider = EmptyCalendarProvider()

    result = CalendarPollingService.sync_connection(
        connection_id=connection.pk,
        now=NOW,
        lookback=timedelta(days=30),
        lookahead=timedelta(days=90),
        provider_factory=cast(CalendarProviderFactory, lambda _connection: provider),
    )

    connection.refresh_from_db()
    assert result.connection_id == connection.pk
    assert provider.query.starts_at_or_after == NOW - timedelta(days=30)
    assert provider.query.starts_before == NOW + timedelta(days=90)
    assert connection.status == "ready"
    assert connection.sync_cursor == "poll-cursor"
    assert connection.last_synced_at is not None


@override_settings(CALENDAR_POLL_ENABLED=True, CALENDAR_POLL_INTERVAL_SECONDS=300)
def test_dispatcher_enqueues_each_due_connection_without_running_provider_inline() -> None:
    user = User.objects.create_user("poll-dispatch")
    connection = create_connection(user)
    make_due(connection)

    with (
        patch("apps.integrations.tasks.timezone.now", return_value=NOW),
        patch("apps.integrations.tasks.sync_calendar_connection.delay") as enqueue,
    ):
        queued = dispatch_calendar_polls.run()

    assert queued == 1
    enqueue.assert_called_once_with(str(connection.pk))
