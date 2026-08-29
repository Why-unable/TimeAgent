from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from django.contrib.auth.models import User
from django.db import transaction

from apps.accounts.services import GuestAccountPolicyService
from apps.events.models import (
    CalendarEvent,
    CalendarEventStatus,
    CalendarEventVisibility,
    EventSeries,
)
from apps.tasks.models import Task
from common.clock import SystemClock
from common.database_locks import lock_user_schedule_writes
from common.time import to_utc


class EventVersionConflictError(ValueError):
    pass


class PastEventMutationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class EventConflict:
    event_id: UUID
    title: str
    start_at: datetime
    end_at: datetime

    def as_dict(self) -> dict[str, str]:
        return {
            "id": str(self.event_id),
            "title": self.title,
            "start_at": self.start_at.isoformat(),
            "end_at": self.end_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class EventImpactPreview:
    start_at: datetime
    end_at: datetime
    conflicts: tuple[EventConflict, ...]

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


class EventConflictError(ValueError):
    def __init__(self, preview: EventImpactPreview) -> None:
        self.preview = preview
        titles = ", ".join(conflict.title for conflict in preview.conflicts[:3])
        suffix = "" if len(preview.conflicts) <= 3 else " and more"
        super().__init__(f"Event conflicts with: {titles}{suffix}")


@dataclass(frozen=True, slots=True)
class CreateEventCommand:
    user: User
    title: str
    start_at: datetime
    end_at: datetime
    timezone: str
    task: Task | None = None
    series: EventSeries | None = None
    description: str = ""
    location: str = ""
    status: CalendarEventStatus | str = CalendarEventStatus.CONFIRMED
    visibility: CalendarEventVisibility | str = CalendarEventVisibility.PRIVATE
    recurrence_rule: str = ""
    source: str = "local"
    external_id: str = ""
    external_account_reference: str = ""
    external_calendar_id: str = ""
    created_by: User | None = None
    origin: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateEventCommand:
    user: User
    event_id: UUID
    expected_version: int
    changes: Mapping[str, Any]
    origin: str = "web"
    current_datetime: datetime | None = None


@dataclass(frozen=True, slots=True)
class EventQuery:
    user: User
    starts_before: datetime | None = None
    ends_after: datetime | None = None
    statuses: tuple[CalendarEventStatus | str, ...] = field(default_factory=tuple)


class EventService:
    UPDATE_FIELDS = frozenset(
        {
            "title",
            "description",
            "start_at",
            "end_at",
            "timezone",
            "location",
            "status",
            "visibility",
            "recurrence_rule",
            "task",
        }
    )

    @staticmethod
    @transaction.atomic
    def create_event(command: CreateEventCommand) -> CalendarEvent:
        EventService._ensure_persisted_user(command.user)
        created_by = command.created_by or command.user
        EventService._ensure_persisted_user(created_by)
        GuestAccountPolicyService.assert_resource_creation_allowed(command.user, "event")
        EventService._lock_schedule(command.user)

        event = CalendarEvent(
            user=command.user,
            task=command.task,
            series=command.series,
            created_by=created_by,
            title=command.title,
            description=command.description,
            start_at=command.start_at,
            end_at=command.end_at,
            timezone=command.timezone,
            location=command.location,
            status=command.status,
            visibility=command.visibility,
            recurrence_rule=command.recurrence_rule,
            source=command.source,
            external_id=command.external_id,
            external_account_reference=command.external_account_reference,
            external_calendar_id=command.external_calendar_id,
        )
        event.full_clean()
        if event.status != CalendarEventStatus.CANCELLED:
            EventService._assert_conflict_free(
                user=command.user,
                start_at=event.start_at,
                end_at=event.end_at,
            )
        event.save(force_insert=True)
        from apps.reminders.scheduling import ReminderScheduleService

        ReminderScheduleService.sync_event_reminders(event=event)
        EventService._record_change(
            event=event,
            operation="created",
            origin=command.origin or ("external_calendar" if event.source != "local" else "web"),
            old_snapshot={},
        )
        return event

    @staticmethod
    @transaction.atomic
    def update_event(command: UpdateEventCommand) -> CalendarEvent:
        EventService._ensure_persisted_user(command.user)
        EventService._validate_changes(command.changes)
        EventService._lock_schedule(command.user)
        event = CalendarEvent.objects.select_for_update().get(
            pk=command.event_id,
            user=command.user,
        )
        EventService._ensure_version(event, command.expected_version)
        EventService._ensure_event_is_mutable(
            event,
            current_datetime=command.current_datetime,
        )
        old_snapshot = EventService._snapshot(event)

        for field_name, value in command.changes.items():
            setattr(event, field_name, value)
        event.version += 1
        event.full_clean()
        if event.status != CalendarEventStatus.CANCELLED:
            EventService._assert_conflict_free(
                user=command.user,
                start_at=event.start_at,
                end_at=event.end_at,
                exclude_event_id=event.pk,
            )
        event.save()
        from apps.reminders.scheduling import ReminderScheduleService

        ReminderScheduleService.sync_event_reminders(event=event)
        EventService._record_change(
            event=event,
            operation="updated",
            origin=command.origin,
            old_snapshot=old_snapshot,
        )
        return event

    @staticmethod
    @transaction.atomic
    def cancel_event(
        *,
        event_id: UUID,
        user: User,
        expected_version: int,
        origin: str = "web",
        current_datetime: datetime | None = None,
    ) -> CalendarEvent:
        EventService._ensure_persisted_user(user)
        EventService._lock_schedule(user)
        event = CalendarEvent.objects.select_for_update().get(pk=event_id, user=user)
        EventService._ensure_version(event, expected_version)
        if event.status == CalendarEventStatus.CANCELLED:
            return event
        EventService._ensure_event_is_mutable(event, current_datetime=current_datetime)

        old_snapshot = EventService._snapshot(event)
        event.status = CalendarEventStatus.CANCELLED
        event.version += 1
        event.full_clean()
        event.save()
        from apps.reminders.scheduling import ReminderScheduleService

        ReminderScheduleService.cancel_event_reminders(event=event)
        EventService._record_change(
            event=event,
            operation="cancelled",
            origin=origin,
            old_snapshot=old_snapshot,
        )
        return event

    @staticmethod
    @transaction.atomic
    def create_events(*, commands: list[CreateEventCommand]) -> list[CalendarEvent]:
        """Create a finite, all-or-nothing set of non-overlapping events.

        Each member still uses the same service invariant as a single event.  A
        failure (including an overlap with an earlier member) rolls back the
        whole batch.
        """

        if not commands:
            raise ValueError("At least one event is required")
        user = commands[0].user
        if any(command.user.pk != user.pk for command in commands):
            raise ValueError("All batch events must belong to the same user")
        return [EventService.create_event(command) for command in commands]

    @staticmethod
    def list_events(query: EventQuery) -> list[CalendarEvent]:
        EventService._ensure_persisted_user(query.user)
        events = CalendarEvent.objects.filter(user=query.user)
        if query.starts_before is not None:
            events = events.filter(start_at__lt=to_utc(query.starts_before))
        if query.ends_after is not None:
            events = events.filter(end_at__gt=to_utc(query.ends_after))
        if query.statuses:
            events = events.filter(status__in=query.statuses)
        return list(events)

    @staticmethod
    def get_event(*, user: User, event_id: UUID) -> CalendarEvent:
        EventService._ensure_persisted_user(user)
        return CalendarEvent.objects.get(pk=event_id, user=user)

    @staticmethod
    def detect_conflicts(
        *,
        user: User,
        start_at: datetime,
        end_at: datetime,
        exclude_event_id: UUID | None = None,
    ) -> list[CalendarEvent]:
        EventService._ensure_persisted_user(user)
        start_at_utc = to_utc(start_at)
        end_at_utc = to_utc(end_at)
        if end_at_utc <= start_at_utc:
            raise ValueError("end_at must be later than start_at")

        conflicts = CalendarEvent.objects.filter(
            user=user,
            start_at__lt=end_at_utc,
            end_at__gt=start_at_utc,
        ).exclude(status=CalendarEventStatus.CANCELLED)
        if exclude_event_id is not None:
            conflicts = conflicts.exclude(pk=exclude_event_id)
        return list(conflicts)

    @staticmethod
    def preview_event_change(
        *,
        user: User,
        start_at: datetime,
        end_at: datetime,
        exclude_event_id: UUID | None = None,
    ) -> EventImpactPreview:
        """Return read-only conflict information for a proposed event time range."""

        conflicts = EventService.detect_conflicts(
            user=user,
            start_at=start_at,
            end_at=end_at,
            exclude_event_id=exclude_event_id,
        )
        return EventImpactPreview(
            start_at=to_utc(start_at),
            end_at=to_utc(end_at),
            conflicts=tuple(
                EventConflict(
                    event_id=event.pk,
                    title=event.title,
                    start_at=event.start_at,
                    end_at=event.end_at,
                )
                for event in conflicts
            ),
        )

    @staticmethod
    def _assert_conflict_free(
        *,
        user: User,
        start_at: datetime,
        end_at: datetime,
        exclude_event_id: UUID | None = None,
    ) -> None:
        preview = EventService.preview_event_change(
            user=user,
            start_at=start_at,
            end_at=end_at,
            exclude_event_id=exclude_event_id,
        )
        if preview.has_conflicts:
            raise EventConflictError(preview)

    @staticmethod
    def _lock_schedule(user: User) -> None:
        lock_user_schedule_writes(user)

    @staticmethod
    def _validate_changes(changes: Mapping[str, Any]) -> None:
        unsupported_fields = set(changes) - EventService.UPDATE_FIELDS
        if unsupported_fields:
            fields = ", ".join(sorted(unsupported_fields))
            raise ValueError(f"Unsupported event fields: {fields}")

    @staticmethod
    def _ensure_version(event: CalendarEvent, expected_version: int) -> None:
        if event.version != expected_version:
            raise EventVersionConflictError(
                f"Event version conflict: expected {expected_version}, current {event.version}"
            )

    @staticmethod
    def _ensure_event_is_mutable(
        event: CalendarEvent,
        *,
        current_datetime: datetime | None,
    ) -> None:
        now = SystemClock().now_utc() if current_datetime is None else to_utc(current_datetime)
        if event.end_at <= now:
            raise PastEventMutationError("已结束的日程只读，不能修改或取消")

    @staticmethod
    def _ensure_persisted_user(user: User) -> None:
        if user.pk is None:
            raise ValueError("Event user must be persisted")

    @staticmethod
    def _snapshot(event: CalendarEvent) -> dict[str, Any]:
        from apps.time_memory.event_handler import json_snapshot

        return json_snapshot(
            event,
            (
                "title",
                "start_at",
                "end_at",
                "timezone",
                "location",
                "status",
                "source",
                "external_account_reference",
                "external_calendar_id",
            ),
        )

    @staticmethod
    def _record_change(
        *,
        event: CalendarEvent,
        operation: str,
        origin: str,
        old_snapshot: dict[str, Any],
    ) -> None:
        from apps.time_memory.event_handler import record_schedule_change

        record_schedule_change(
            user=event.user,
            entity_type="event",
            entity_id=event.pk,
            operation=operation,
            source=origin,
            old_snapshot=old_snapshot,
            new_snapshot=EventService._snapshot(event),
        )
