from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from django.db import transaction

from apps.notifications.integrations import create_reminder_deliveries
from apps.reminders.models import Reminder, ReminderStatus


class ReminderDeliveryError(RuntimeError):
    pass


class ReminderDispatcher:
    @staticmethod
    def dispatch_due_reminders(
        *,
        now: datetime,
        enqueue: Callable[[UUID], object],
        batch_size: int = 100,
    ) -> int:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")

        with transaction.atomic():
            reminders = list(
                Reminder.objects.select_for_update(skip_locked=True)
                .filter(
                    status=ReminderStatus.PENDING,
                    trigger_at__lte=now,
                )
                .order_by("trigger_at", "id")[:batch_size]
            )
            reminder_ids = [reminder.id for reminder in reminders]
            for reminder in reminders:
                reminder.transition_to(ReminderStatus.QUEUED, occurred_at=now)
                reminder.updated_at = now
            Reminder.objects.bulk_update(
                reminders,
                fields=["status", "queued_at", "updated_at"],
            )

        for reminder_id in reminder_ids:
            enqueue(reminder_id)

        return len(reminder_ids)

    @staticmethod
    def send_reminder(
        reminder_id: UUID,
        *,
        now: datetime,
    ) -> bool:
        delivery_error: ReminderDeliveryError | None = None
        with transaction.atomic():
            reminder = (
                Reminder.objects.select_for_update().select_related("user").get(pk=reminder_id)
            )
            if reminder.status in {
                ReminderStatus.SENDING,
                ReminderStatus.SENT,
                ReminderStatus.CANCELLED,
            }:
                return False
            if reminder.status == ReminderStatus.PENDING:
                return False
            if reminder.status == ReminderStatus.FAILED:
                reminder.transition_to(ReminderStatus.QUEUED, occurred_at=now)
            reminder.transition_to(ReminderStatus.SENDING, occurred_at=now)

            try:
                create_reminder_deliveries(reminder=reminder, occurred_at=now)
            except Exception as exc:
                delivery_error = (
                    exc
                    if isinstance(exc, ReminderDeliveryError)
                    else ReminderDeliveryError(str(exc) or exc.__class__.__name__)
                )
                reminder.transition_to(
                    ReminderStatus.FAILED,
                    occurred_at=now,
                    failure_reason=str(delivery_error),
                )
            else:
                # Reminder SENT means the due occurrence was handed to the durable
                # notification subsystem. Individual channel outcomes are tracked
                # independently by NotificationDelivery.
                reminder.transition_to(ReminderStatus.SENT, occurred_at=now)

            reminder.full_clean()
            reminder.save(
                update_fields=[
                    "status",
                    "queued_at",
                    "sent_at",
                    "retry_count",
                    "failure_reason",
                    "updated_at",
                ]
            )

        if delivery_error is not None:
            raise delivery_error
        return True
