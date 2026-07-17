from uuid import UUID

from celery import shared_task
from django.utils import timezone

from apps.reminders.dispatcher import ReminderDeliveryError, ReminderDispatcher


@shared_task(name="reminders.dispatch_due")  # type: ignore[untyped-decorator]
def dispatch_due_reminders(batch_size: int = 100) -> int:
    return ReminderDispatcher.dispatch_due_reminders(
        now=timezone.now(),
        batch_size=batch_size,
        enqueue=lambda reminder_id: send_reminder.delay(str(reminder_id)),
    )


@shared_task(
    bind=True,
    name="reminders.send",
    autoretry_for=(ReminderDeliveryError,),
    retry_backoff=True,
    retry_jitter=False,
    max_retries=3,
)  # type: ignore[untyped-decorator]
def send_reminder(self: object, reminder_id: str) -> bool:
    del self
    return ReminderDispatcher.send_reminder(
        UUID(reminder_id),
        now=timezone.now(),
    )
