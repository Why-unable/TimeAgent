from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from django.contrib.auth.models import User

from apps.integrations.calendar.contracts import ExternalCalendarProvider
from apps.integrations.calendar.dto import ExternalCalendarContext
from apps.integrations.calendar.exceptions import (
    ExternalCalendarError,
    ExternalCalendarPermanentError,
)
from apps.integrations.calendar.providers.google import GoogleCalendarProvider
from apps.integrations.calendar.providers.registry import build_calendar_provider
from apps.integrations.calendar.sync_services import (
    CalendarSyncService,
    SyncExternalCalendarCommand,
)
from common.clock import Clock, SystemClock
from common.time import to_utc

MonotonicClock = Callable[[], float]


@dataclass(frozen=True, slots=True)
class GoogleCalendarVerificationReport:
    status: Literal["pass", "fail"]
    checked_at: datetime
    connection_id: UUID
    starts_at: datetime
    starts_before: datetime
    duration_ms: int
    calendar_count: int
    primary_calendar_count: int
    configured_calendar_accessible: bool
    cursor_present_before: bool
    cursor_present_after: bool
    cursor_was_reset: bool
    fetched_count: int
    created_count: int
    updated_count: int
    cancelled_count: int
    provider_diagnostics: dict[str, object]
    error_type: str = ""
    error: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "report_schema": "google-calendar-verification-v1",
            "status": self.status,
            "checked_at": self.checked_at.isoformat(),
            "connection_id": str(self.connection_id),
            "window": {
                "starts_at": self.starts_at.isoformat(),
                "starts_before": self.starts_before.isoformat(),
            },
            "duration_ms": self.duration_ms,
            "calendar_count": self.calendar_count,
            "primary_calendar_count": self.primary_calendar_count,
            "configured_calendar_accessible": self.configured_calendar_accessible,
            "cursor_present_before": self.cursor_present_before,
            "cursor_present_after": self.cursor_present_after,
            "cursor_was_reset": self.cursor_was_reset,
            "sync": {
                "fetched_count": self.fetched_count,
                "created_count": self.created_count,
                "updated_count": self.updated_count,
                "cancelled_count": self.cancelled_count,
            },
            "provider": self.provider_diagnostics,
            "error_type": self.error_type,
            "error": self.error,
        }


class GoogleCalendarVerificationService:
    @staticmethod
    def verify(
        *,
        user: User,
        connection_id: UUID,
        starts_at: datetime,
        starts_before: datetime,
        provider: ExternalCalendarProvider | None = None,
        clock: Clock | None = None,
        monotonic: MonotonicClock,
    ) -> GoogleCalendarVerificationReport:
        normalized_start = to_utc(starts_at)
        normalized_end = to_utc(starts_before)
        if normalized_start >= normalized_end:
            raise ValueError("starts_before must be later than starts_at")
        connection = CalendarSyncService.get_connection(
            user=user,
            connection_id=connection_id,
        )
        if connection.provider_name != "google":
            raise ValueError("Verification requires a Google Calendar connection")

        current_clock = clock or SystemClock()
        started = monotonic()
        resolved_provider: ExternalCalendarProvider | None = provider
        calendar_count = 0
        primary_calendar_count = 0
        configured_calendar_accessible = False
        cursor_present_before = bool(connection.sync_cursor)
        try:
            if resolved_provider is None:
                resolved_provider = build_calendar_provider(connection)
            if resolved_provider.provider_name != "google":
                raise ValueError("Verification provider must be Google Calendar")
            calendars = resolved_provider.list_calendars(
                ExternalCalendarContext(
                    account_reference=connection.account_reference,
                    timezone=connection.timezone,
                )
            )
            calendar_count = len(calendars)
            primary_calendar_count = sum(calendar.is_primary for calendar in calendars)
            configured_calendar_accessible = any(
                calendar.external_id == connection.calendar_id for calendar in calendars
            )
            if not configured_calendar_accessible:
                raise ExternalCalendarPermanentError(
                    "Configured Google calendar is no longer accessible"
                )
            sync_result = CalendarSyncService.sync(
                SyncExternalCalendarCommand(
                    user=user,
                    connection_id=connection.id,
                    provider=resolved_provider,
                    starts_at_or_after=normalized_start,
                    starts_before=normalized_end,
                )
            )
        except ExternalCalendarError as exc:
            CalendarSyncService.record_connection_error(
                user=user,
                connection_id=connection.id,
                error=exc,
            )
            refreshed_connection = CalendarSyncService.get_connection(
                user=user,
                connection_id=connection.id,
            )
            return GoogleCalendarVerificationReport(
                status="fail",
                checked_at=current_clock.now_utc(),
                connection_id=connection.id,
                starts_at=normalized_start,
                starts_before=normalized_end,
                duration_ms=GoogleCalendarVerificationService._duration_ms(
                    started,
                    monotonic(),
                ),
                calendar_count=calendar_count,
                primary_calendar_count=primary_calendar_count,
                configured_calendar_accessible=configured_calendar_accessible,
                cursor_present_before=cursor_present_before,
                cursor_present_after=bool(refreshed_connection.sync_cursor),
                cursor_was_reset=False,
                fetched_count=0,
                created_count=0,
                updated_count=0,
                cancelled_count=0,
                provider_diagnostics=GoogleCalendarVerificationService._diagnostics(
                    resolved_provider
                ),
                error_type=type(exc).__name__,
                error=str(exc),
            )

        refreshed_connection = CalendarSyncService.get_connection(
            user=user,
            connection_id=connection.id,
        )
        return GoogleCalendarVerificationReport(
            status="pass",
            checked_at=current_clock.now_utc(),
            connection_id=connection.id,
            starts_at=normalized_start,
            starts_before=normalized_end,
            duration_ms=GoogleCalendarVerificationService._duration_ms(
                started,
                monotonic(),
            ),
            calendar_count=calendar_count,
            primary_calendar_count=primary_calendar_count,
            configured_calendar_accessible=True,
            cursor_present_before=cursor_present_before,
            cursor_present_after=bool(refreshed_connection.sync_cursor),
            cursor_was_reset=sync_result.cursor_was_reset,
            fetched_count=sync_result.fetched_count,
            created_count=sync_result.created_count,
            updated_count=sync_result.updated_count,
            cancelled_count=sync_result.cancelled_count,
            provider_diagnostics=GoogleCalendarVerificationService._diagnostics(
                resolved_provider
            ),
        )

    @staticmethod
    def _diagnostics(
        provider: ExternalCalendarProvider | None,
    ) -> dict[str, object]:
        if isinstance(provider, GoogleCalendarProvider):
            return provider.diagnostics().as_dict()
        return {
            "request_count": 0,
            "calendar_pages": 0,
            "event_pages": 0,
            "sync_token_resets": 0,
            "transport_errors": 0,
            "http_status_counts": {},
        }

    @staticmethod
    def _duration_ms(started: float, finished: float) -> int:
        return max(0, round((finished - started) * 1000))
