from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from apps.accounts.services import GuestAccountPolicyService
from apps.events.models import CalendarEvent
from apps.reminders.models import (
    Reminder,
    ReminderChannel,
    ReminderStatus,
    ReminderTargetType,
)
from apps.tasks.models import Task
from common.database_locks import lock_user_schedule_writes
from common.time import to_utc


class ReminderIdempotencyConflictError(ValueError):
    pass


class ReminderCannotCancelError(ValueError):
    pass


class ReminderTriggerNotFutureError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CreateReminderCommand:
    user: User
    title: str
    trigger_at: datetime
    current_time: datetime
    timezone: str
    deduplication_key: str
    channel: ReminderChannel | str = ReminderChannel.CONSOLE
    target_type: ReminderTargetType | str = ReminderTargetType.CUSTOM
    target_id: UUID | None = None
    origin: str = "web"


@dataclass(frozen=True, slots=True)
class ReminderQuery:
    user: User
    statuses: tuple[ReminderStatus | str, ...] = ()
    trigger_before: datetime | None = None


@dataclass(frozen=True, slots=True)
class UpdateReminderCommand:
    user: User
    reminder_id: UUID
    expected_version: int
    changes: Mapping[str, Any]
    current_time: datetime
    origin: str = "web"


class ReminderService:
    UPDATE_FIELDS = frozenset(
        {"title", "trigger_at", "timezone", "channel", "target_type", "target_id"}
    )

    @staticmethod
    def list_reminders(query: ReminderQuery) -> list[Reminder]:
        if query.user.pk is None:
            raise ValueError("Reminder user must be persisted")
        reminders = Reminder.objects.filter(user=query.user)
        if query.statuses:
            reminders = reminders.filter(status__in=query.statuses)
        if query.trigger_before is not None:
            reminders = reminders.filter(trigger_at__lte=query.trigger_before)
        return list(reminders)

    @staticmethod
    def get_reminder(*, user: User, reminder_id: UUID) -> Reminder:
        if user.pk is None:
            raise ValueError("Reminder user must be persisted")
        return Reminder.objects.get(pk=reminder_id, user=user)

    @staticmethod
    @transaction.atomic
    def create_reminder(command: CreateReminderCommand) -> Reminder:
        if command.user.pk is None:
            raise ValueError("Reminder user must be persisted")
        GuestAccountPolicyService.assert_resource_creation_allowed(command.user, "reminder")
        GuestAccountPolicyService.assert_reminder_channel_allowed(command.user, command.channel)
        lock_user_schedule_writes(command.user)
        ReminderService._validate_target(command)

        candidate = Reminder(
            user=command.user,
            title=command.title,
            trigger_at=command.trigger_at,
            timezone=command.timezone,
            channel=command.channel,
            target_type=command.target_type,
            target_id=command.target_id,
            deduplication_key=command.deduplication_key,
        )
        candidate.full_clean(validate_constraints=False)

        existing = Reminder.objects.filter(
            user=command.user,
            deduplication_key=candidate.deduplication_key,
        ).first()
        if existing is not None:
            ReminderService._ensure_matching_payload(existing, candidate)
            return existing

        ReminderService._validate_future_trigger(
            trigger_at=candidate.trigger_at,
            current_time=command.current_time,
        )

        try:
            with transaction.atomic():
                candidate.save(force_insert=True)
        except IntegrityError:
            existing = Reminder.objects.filter(
                user=command.user,
                deduplication_key=candidate.deduplication_key,
            ).first()
            if existing is None:
                raise
            ReminderService._ensure_matching_payload(existing, candidate)
            return existing

        ReminderService._record_change(candidate, "created", command.origin, {})
        return candidate

    @staticmethod
    @transaction.atomic
    def cancel_reminder(
        *,
        reminder_id: UUID,
        user: User,
        occurred_at: datetime,
        origin: str = "web",
    ) -> Reminder:
        if user.pk is None:
            raise ValueError("Reminder user must be persisted")
        lock_user_schedule_writes(user)
        reminder = Reminder.objects.select_for_update().get(
            pk=reminder_id,
            user=user,
        )
        if reminder.status == ReminderStatus.CANCELLED:
            return reminder
        if not reminder.can_transition_to(ReminderStatus.CANCELLED):
            raise ReminderCannotCancelError(
                f"Reminder in {reminder.status} status cannot be cancelled"
            )

        old_snapshot = ReminderService._snapshot(reminder)
        reminder.transition_to(ReminderStatus.CANCELLED, occurred_at=occurred_at)
        reminder.full_clean()
        reminder.version += 1
        reminder.save(update_fields=["status", "version", "updated_at"])
        ReminderService._record_change(
            reminder, "cancelled", origin, old_snapshot, occurred_at=occurred_at
        )
        return reminder

    @staticmethod
    @transaction.atomic
    def update_reminder(command: UpdateReminderCommand) -> Reminder:
        if command.user.pk is None:
            raise ValueError("Reminder user must be persisted")
        if "channel" in command.changes:
            GuestAccountPolicyService.assert_reminder_channel_allowed(
                command.user, command.changes["channel"]
            )
        lock_user_schedule_writes(command.user)
        unsupported = set(command.changes) - ReminderService.UPDATE_FIELDS
        if unsupported:
            raise ValueError(f"Unsupported reminder fields: {', '.join(sorted(unsupported))}")
        reminder = Reminder.objects.select_for_update().get(
            pk=command.reminder_id,
            user=command.user,
        )
        if reminder.version != command.expected_version:
            raise ValueError(
                "Reminder version conflict: "
                f"expected {command.expected_version}, current {reminder.version}"
            )
        if reminder.status not in {ReminderStatus.PENDING, ReminderStatus.FAILED}:
            raise ValueError("Only pending or failed reminders can be edited")
        old_snapshot = ReminderService._snapshot(reminder)
        for field_name, value in command.changes.items():
            setattr(reminder, field_name, value)
        ReminderService._validate_target_values(
            user=command.user,
            target_type=reminder.target_type,
            target_id=reminder.target_id,
        )
        reminder.version += 1
        reminder.full_clean()
        if "trigger_at" in command.changes:
            ReminderService._validate_future_trigger(
                trigger_at=reminder.trigger_at,
                current_time=command.current_time,
            )
        reminder.save()
        ReminderService._record_change(reminder, "updated", command.origin, old_snapshot)
        return reminder

    @staticmethod
    def _snapshot(reminder: Reminder) -> dict[str, Any]:
        from apps.time_memory.event_handler import json_snapshot

        return json_snapshot(
            reminder,
            ("title", "trigger_at", "timezone", "status", "target_type", "target_id"),
        )

    @staticmethod
    def _record_change(
        reminder: Reminder,
        operation: str,
        origin: str,
        old_snapshot: dict[str, Any],
        *,
        occurred_at: datetime | None = None,
    ) -> None:
        from apps.time_memory.event_handler import record_schedule_change

        record_schedule_change(
            user=reminder.user,
            entity_type="reminder",
            entity_id=reminder.pk,
            operation=operation,
            source=origin,
            old_snapshot=old_snapshot,
            new_snapshot=ReminderService._snapshot(reminder),
            occurred_at=occurred_at,
        )

    @staticmethod
    def _ensure_matching_payload(existing: Reminder, candidate: Reminder) -> None:
        fields = (
            "title",
            "trigger_at",
            "timezone",
            "channel",
            "target_type",
            "target_id",
        )
        mismatched_fields = [
            field_name
            for field_name in fields
            if getattr(existing, field_name) != getattr(candidate, field_name)
        ]
        if mismatched_fields:
            fields_text = ", ".join(mismatched_fields)
            raise ReminderIdempotencyConflictError(
                f"Idempotency key already exists with different reminder data: {fields_text}"
            )

    @staticmethod
    def _validate_target(command: CreateReminderCommand) -> None:
        ReminderService._validate_target_values(
            user=command.user,
            target_type=command.target_type,
            target_id=command.target_id,
        )

    @staticmethod
    def _validate_future_trigger(*, trigger_at: datetime, current_time: datetime) -> None:
        if to_utc(trigger_at) <= to_utc(current_time):
            raise ReminderTriggerNotFutureError("Reminder time must be in the future")

    @staticmethod
    def _validate_target_values(*, user: User, target_type: str, target_id: UUID | None) -> None:
        if target_type == ReminderTargetType.CUSTOM:
            return
        if target_id is None:
            return
        model = CalendarEvent if target_type == ReminderTargetType.CALENDAR_EVENT else Task
        if not model.objects.filter(pk=target_id, user=user).exists():
            raise ValueError("Reminder target must belong to the current user")
