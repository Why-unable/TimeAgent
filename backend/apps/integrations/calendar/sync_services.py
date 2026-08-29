from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from apps.events.models import CalendarEvent, CalendarEventStatus, CalendarEventVisibility
from apps.events.services import EventService
from apps.integrations.calendar.contracts import ExternalCalendarProvider
from apps.integrations.calendar.dto import (
    ExternalCalendarContext,
    ExternalEventQuery,
    ExternalEventTombstone,
)
from apps.integrations.calendar.exceptions import ExternalCalendarError
from apps.integrations.models import CalendarSyncConnection, CalendarSyncStatus
from apps.reminders.scheduling import ReminderScheduleService
from common.database_locks import lock_user_schedule_writes
from common.time import to_utc


class CalendarSyncUnavailableError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SyncExternalCalendarCommand:
    user: User
    connection_id: UUID
    provider: ExternalCalendarProvider
    starts_at_or_after: datetime
    starts_before: datetime


@dataclass(frozen=True, slots=True)
class CalendarSyncResult:
    connection_id: UUID
    fetched_count: int
    created_count: int
    updated_count: int
    cancelled_count: int
    synced_at: datetime
    cursor_was_reset: bool


class CalendarSyncService:
    @staticmethod
    @transaction.atomic
    def create_connection(
        *,
        user: User,
        provider_name: str,
        account_reference: str,
        calendar_id: str,
        calendar_name: str,
        timezone_name: str,
        enabled: bool = True,
    ) -> CalendarSyncConnection:
        connection = CalendarSyncConnection(
            user=user,
            provider_name=provider_name,
            account_reference=account_reference,
            calendar_id=calendar_id,
            calendar_name=calendar_name,
            timezone=timezone_name,
            enabled=enabled,
        )
        connection.full_clean()
        connection.save(force_insert=True)
        return connection

    @staticmethod
    @transaction.atomic
    def upsert_connection(
        *,
        user: User,
        provider_name: str,
        account_reference: str,
        calendar_id: str,
        calendar_name: str,
        timezone_name: str,
        enabled: bool = True,
    ) -> CalendarSyncConnection:
        connection = CalendarSyncConnection.objects.select_for_update().filter(
            user=user,
            provider_name=provider_name,
            account_reference=account_reference,
            calendar_id=calendar_id,
        ).first()
        if connection is None:
            return CalendarSyncService.create_connection(
                user=user,
                provider_name=provider_name,
                account_reference=account_reference,
                calendar_id=calendar_id,
                calendar_name=calendar_name,
                timezone_name=timezone_name,
                enabled=enabled,
            )
        connection.calendar_name = calendar_name
        connection.timezone = timezone_name
        connection.enabled = enabled
        connection.status = CalendarSyncStatus.READY if enabled else CalendarSyncStatus.DISABLED
        connection.last_error = ""
        connection.full_clean()
        connection.save(
            update_fields=[
                "calendar_name",
                "timezone",
                "enabled",
                "status",
                "last_error",
                "updated_at",
            ]
        )
        return connection

    @staticmethod
    def sync(command: SyncExternalCalendarCommand) -> CalendarSyncResult:
        try:
            return CalendarSyncService._sync_atomic(command)
        except CalendarSyncUnavailableError:
            raise
        except Exception as exc:
            CalendarSyncConnection.objects.filter(
                pk=command.connection_id,
                user=command.user,
            ).update(
                status=CalendarSyncStatus.ERROR,
                last_error=CalendarSyncService._public_error_message(exc),
                updated_at=timezone.now(),
            )
            raise

    @staticmethod
    def _public_error_message(exc: Exception) -> str:
        if isinstance(exc, ExternalCalendarError):
            return str(exc)[:4000]
        return "Calendar provider sync failed"

    @staticmethod
    @transaction.atomic
    def _sync_atomic(command: SyncExternalCalendarCommand) -> CalendarSyncResult:
        if command.user.pk is None:
            raise ValueError("Calendar sync user must be persisted")
        connection = CalendarSyncConnection.objects.select_for_update().get(
            pk=command.connection_id,
            user=command.user,
        )
        if not connection.enabled:
            raise CalendarSyncUnavailableError("Calendar sync connection is disabled")
        if not command.provider.get_capabilities().read_events:
            raise CalendarSyncUnavailableError("Calendar provider does not support read_events")

        starts_at_or_after = to_utc(command.starts_at_or_after)
        starts_before = to_utc(command.starts_before)
        if starts_before <= starts_at_or_after:
            raise ValueError("starts_before must be later than starts_at_or_after")
        external_page = command.provider.list_events(
            ExternalCalendarContext(
                account_reference=connection.account_reference,
                timezone=connection.timezone,
            ),
            ExternalEventQuery(
                calendar_id=connection.calendar_id,
                starts_at_or_after=starts_at_or_after,
                starts_before=starts_before,
                sync_cursor=connection.sync_cursor,
            ),
        )

        lock_user_schedule_writes(command.user)
        created_count = updated_count = cancelled_count = 0
        fetched_external_ids: set[str] = set()
        for external_event in external_page.events:
            if external_event.calendar_id != connection.calendar_id:
                continue
            fetched_external_ids.add(external_event.external_id)
            if isinstance(external_event, ExternalEventTombstone):
                if CalendarSyncService._cancel_tombstone(
                    user=command.user,
                    provider_name=command.provider.provider_name,
                    account_reference=connection.account_reference,
                    calendar_id=connection.calendar_id,
                    external_id=external_event.external_id,
                ):
                    updated_count += 1
                    cancelled_count += 1
                continue
            event, was_created, was_cancelled = CalendarSyncService._upsert_event(
                user=command.user,
                provider_name=command.provider.provider_name,
                account_reference=connection.account_reference,
                external_event=external_event,
            )
            del event
            if was_created:
                created_count += 1
            else:
                updated_count += 1
            if was_cancelled:
                cancelled_count += 1

        if external_page.cursor_was_reset:
            missing_ids = CalendarSyncService._missing_external_ids_after_reset(
                user=command.user,
                provider_name=command.provider.provider_name,
                account_reference=connection.account_reference,
                calendar_id=connection.calendar_id,
                starts_at_or_after=starts_at_or_after,
                starts_before=starts_before,
                fetched_external_ids=fetched_external_ids,
            )
            for external_id in missing_ids:
                if CalendarSyncService._cancel_tombstone(
                    user=command.user,
                    provider_name=command.provider.provider_name,
                    account_reference=connection.account_reference,
                    calendar_id=connection.calendar_id,
                    external_id=external_id,
                ):
                    updated_count += 1
                    cancelled_count += 1

        synced_at = timezone.now()
        connection.sync_cursor = external_page.next_sync_cursor or starts_before.isoformat()
        connection.last_synced_at = synced_at
        connection.last_error = ""
        connection.status = CalendarSyncStatus.READY
        connection.save(
            update_fields=[
                "sync_cursor",
                "last_synced_at",
                "last_error",
                "status",
                "updated_at",
            ]
        )
        return CalendarSyncResult(
            connection_id=connection.pk,
            fetched_count=len(external_page.events),
            created_count=created_count,
            updated_count=updated_count,
            cancelled_count=cancelled_count,
            synced_at=synced_at,
            cursor_was_reset=external_page.cursor_was_reset,
        )

    @staticmethod
    def list_connections(*, user: User) -> list[CalendarSyncConnection]:
        if user.pk is None:
            raise ValueError("Calendar sync user must be persisted")
        return list(CalendarSyncConnection.objects.filter(user=user))

    @staticmethod
    def get_connection(*, user: User, connection_id: UUID) -> CalendarSyncConnection:
        if user.pk is None:
            raise ValueError("Calendar sync user must be persisted")
        return CalendarSyncConnection.objects.get(pk=connection_id, user=user)

    @staticmethod
    def record_connection_error(
        *,
        user: User,
        connection_id: UUID,
        error: Exception,
    ) -> None:
        CalendarSyncConnection.objects.filter(pk=connection_id, user=user).update(
            status=CalendarSyncStatus.ERROR,
            last_error=CalendarSyncService._public_error_message(error),
            updated_at=timezone.now(),
        )

    @staticmethod
    def _upsert_event(
        *,
        user: User,
        provider_name: str,
        account_reference: str,
        external_event: Any,
    ) -> tuple[CalendarEvent, bool, bool]:
        status = CalendarSyncService._event_status(external_event.status)
        event = CalendarEvent.objects.select_for_update().filter(
            user=user,
            source=provider_name,
            external_account_reference=account_reference,
            external_calendar_id=external_event.calendar_id,
            external_id=external_event.external_id,
        ).first()
        old_snapshot = EventService._snapshot(event) if event is not None else {}
        was_created = event is None
        if event is None:
            event = CalendarEvent(
                user=user,
                title=external_event.title,
                description=external_event.description,
                start_at=external_event.starts_at,
                end_at=external_event.ends_at,
                timezone=external_event.timezone,
                location=external_event.location,
                status=status,
                visibility=CalendarEventVisibility.PRIVATE,
                source=provider_name,
                external_id=external_event.external_id,
                external_account_reference=account_reference,
                external_calendar_id=external_event.calendar_id,
                created_by=user,
            )
            event.full_clean()
            event.save(force_insert=True)
            operation = "created"
        else:
            event.title = external_event.title
            event.description = external_event.description
            event.start_at = external_event.starts_at
            event.end_at = external_event.ends_at
            event.timezone = external_event.timezone
            event.location = external_event.location
            event.status = status
            event.version += 1
            event.full_clean()
            event.save()
            operation = "updated"
        ReminderScheduleService.sync_event_reminders(event=event)
        EventService._record_change(
            event=event,
            operation=operation,
            origin="external_calendar_sync",
            old_snapshot=old_snapshot,
        )
        return event, was_created, status == CalendarEventStatus.CANCELLED

    @staticmethod
    def _cancel_tombstone(
        *,
        user: User,
        provider_name: str,
        account_reference: str,
        calendar_id: str,
        external_id: str,
    ) -> bool:
        event = CalendarEvent.objects.select_for_update().filter(
            user=user,
            source=provider_name,
            external_account_reference=account_reference,
            external_calendar_id=calendar_id,
            external_id=external_id,
        ).first()
        if event is None or event.status == CalendarEventStatus.CANCELLED:
            return False
        old_snapshot = EventService._snapshot(event)
        event.status = CalendarEventStatus.CANCELLED
        event.version += 1
        event.full_clean()
        event.save()
        ReminderScheduleService.sync_event_reminders(event=event)
        EventService._record_change(
            event=event,
            operation="updated",
            origin="external_calendar_sync",
            old_snapshot=old_snapshot,
        )
        return True

    @staticmethod
    def _missing_external_ids_after_reset(
        *,
        user: User,
        provider_name: str,
        account_reference: str,
        calendar_id: str,
        starts_at_or_after: datetime,
        starts_before: datetime,
        fetched_external_ids: set[str],
    ) -> list[str]:
        events = CalendarEvent.objects.filter(
            user=user,
            source=provider_name,
            external_account_reference=account_reference,
            external_calendar_id=calendar_id,
            start_at__lt=starts_before,
            end_at__gt=starts_at_or_after,
        ).exclude(status=CalendarEventStatus.CANCELLED)
        if fetched_external_ids:
            events = events.exclude(external_id__in=fetched_external_ids)
        return list(events.values_list("external_id", flat=True))

    @staticmethod
    def _event_status(value: str) -> CalendarEventStatus:
        normalized = value.strip().lower()
        if normalized == CalendarEventStatus.CANCELLED:
            return CalendarEventStatus.CANCELLED
        if normalized == CalendarEventStatus.TENTATIVE:
            return CalendarEventStatus.TENTATIVE
        return CalendarEventStatus.CONFIRMED
