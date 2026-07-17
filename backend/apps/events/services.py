from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from django.contrib.auth.models import User
from django.db import transaction

from apps.events.models import (
    CalendarEvent,
    CalendarEventStatus,
    CalendarEventVisibility,
)
from common.time import to_utc


class EventVersionConflictError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CreateEventCommand:
    user: User
    title: str
    start_at: datetime
    end_at: datetime
    timezone: str
    description: str = ""
    location: str = ""
    status: CalendarEventStatus | str = CalendarEventStatus.CONFIRMED
    visibility: CalendarEventVisibility | str = CalendarEventVisibility.PRIVATE
    recurrence_rule: str = ""
    source: str = "local"
    external_id: str = ""
    created_by: User | None = None


@dataclass(frozen=True, slots=True)
class UpdateEventCommand:
    user: User
    event_id: UUID
    expected_version: int
    changes: Mapping[str, Any]


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
            "source",
            "external_id",
        }
    )

    @staticmethod
    @transaction.atomic
    def create_event(command: CreateEventCommand) -> CalendarEvent:
        EventService._ensure_persisted_user(command.user)
        created_by = command.created_by or command.user
        EventService._ensure_persisted_user(created_by)

        event = CalendarEvent(
            user=command.user,
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
        )
        event.full_clean()
        event.save(force_insert=True)
        return event

    @staticmethod
    @transaction.atomic
    def update_event(command: UpdateEventCommand) -> CalendarEvent:
        EventService._ensure_persisted_user(command.user)
        EventService._validate_changes(command.changes)
        event = CalendarEvent.objects.select_for_update().get(
            pk=command.event_id,
            user=command.user,
        )
        EventService._ensure_version(event, command.expected_version)

        for field_name, value in command.changes.items():
            setattr(event, field_name, value)
        event.version += 1
        event.full_clean()
        event.save()
        return event

    @staticmethod
    @transaction.atomic
    def cancel_event(
        *,
        event_id: UUID,
        user: User,
        expected_version: int,
    ) -> CalendarEvent:
        EventService._ensure_persisted_user(user)
        event = CalendarEvent.objects.select_for_update().get(pk=event_id, user=user)
        EventService._ensure_version(event, expected_version)
        if event.status == CalendarEventStatus.CANCELLED:
            return event

        event.status = CalendarEventStatus.CANCELLED
        event.version += 1
        event.full_clean()
        event.save()
        return event

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
    def _ensure_persisted_user(user: User) -> None:
        if user.pk is None:
            raise ValueError("Event user must be persisted")
