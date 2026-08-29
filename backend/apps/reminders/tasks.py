from datetime import timedelta
from uuid import UUID

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.reminders.dispatcher import ReminderDeliveryError, ReminderDispatcher


@shared_task(name="reminders.dispatch_due")  # type: ignore[untyped-decorator]
def dispatch_due_reminders(batch_size: int = 100) -> int:
    max_lateness = timedelta(seconds=settings.REMINDER_MAX_LATENESS_SECONDS)
    return ReminderDispatcher.dispatch_due_reminders(
        now=timezone.now(),
        batch_size=batch_size,
        max_lateness=max_lateness,
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
        max_lateness=timedelta(seconds=settings.REMINDER_MAX_LATENESS_SECONDS),
    )
