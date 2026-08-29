from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

from django.contrib.auth.models import User

from apps.integrations.calendar.contracts import ExternalCalendarProvider
from apps.integrations.calendar.providers.registry import build_calendar_provider
from apps.integrations.calendar.sync_services import (
    CalendarSyncResult,
    CalendarSyncService,
    SyncExternalCalendarCommand,
)
from apps.integrations.models import CalendarSyncConnection
from common.time import to_utc

CalendarProviderFactory = Callable[[CalendarSyncConnection], ExternalCalendarProvider]


class CalendarPollingService:
    """Deterministically selects and syncs bounded read-only calendar connections."""

    @staticmethod
    def list_due_connection_ids(
        *,
        now: datetime,
        minimum_interval: timedelta,
        batch_size: int,
    ) -> list[UUID]:
        if minimum_interval <= timedelta(0):
            raise ValueError("minimum_interval must be positive")
        if batch_size < 1 or batch_size > 1000:
            raise ValueError("batch_size must be between 1 and 1000")
        cutoff = to_utc(now) - minimum_interval
        return list(
            CalendarSyncConnection.objects.filter(
                enabled=True,
                updated_at__lte=cutoff,
            )
            .order_by("last_synced_at", "updated_at", "id")
            .values_list("id", flat=True)[:batch_size]
        )

    @staticmethod
    def sync_connection(
        *,
        connection_id: UUID,
        now: datetime,
        lookback: timedelta,
        lookahead: timedelta,
        provider_factory: CalendarProviderFactory = build_calendar_provider,
    ) -> CalendarSyncResult:
        if lookback < timedelta(0):
            raise ValueError("lookback cannot be negative")
        if lookahead <= timedelta(0):
            raise ValueError("lookahead must be positive")
        connection = CalendarSyncConnection.objects.select_related("user").get(
            pk=connection_id
        )
        user = connection.user
        if not isinstance(user, User):
            raise ValueError("Calendar sync connection requires a persisted user")
        anchor = to_utc(now)
        return CalendarSyncService.sync(
            SyncExternalCalendarCommand(
                user=user,
                connection_id=connection.pk,
                provider=provider_factory(connection),
                starts_at_or_after=anchor - lookback,
                starts_before=anchor + lookahead,
            )
        )
