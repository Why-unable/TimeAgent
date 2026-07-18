from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from apps.reminders.models import (
    Reminder,
    ReminderChannel,
    ReminderStatus,
    ReminderTargetType,
)


class ReminderIdempotencyConflictError(ValueError):
    pass


class ReminderCannotCancelError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CreateReminderCommand:
    user: User
    title: str
    trigger_at: datetime
    timezone: str
    deduplication_key: str
    channel: ReminderChannel | str = ReminderChannel.CONSOLE
    target_type: ReminderTargetType | str = ReminderTargetType.CUSTOM
    target_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ReminderQuery:
    user: User
    statuses: tuple[ReminderStatus | str, ...] = ()
    trigger_before: datetime | None = None


class ReminderService:
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

        return candidate

    @staticmethod
    @transaction.atomic
    def cancel_reminder(
        *,
        reminder_id: UUID,
        user: User,
        occurred_at: datetime,
    ) -> Reminder:
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

        reminder.transition_to(ReminderStatus.CANCELLED, occurred_at=occurred_at)
        reminder.full_clean()
        reminder.save(update_fields=["status", "updated_at"])
        return reminder

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
