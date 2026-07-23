from datetime import datetime

from apps.briefings.models import BriefingRun
from apps.notifications.dispatcher import NotificationDispatcher
from apps.notifications.models import NotificationDelivery, NotificationSourceType
from apps.notifications.services import CreateDeliveryCommand, NotificationService
from apps.reminders.models import Reminder


def create_reminder_deliveries(
    *, reminder: Reminder, occurred_at: datetime
) -> list[NotificationDelivery]:
    deliveries: list[NotificationDelivery] = []
    for channel in NotificationService.channels_for(
        user=reminder.user, source_type=NotificationSourceType.REMINDER
    ):
        delivery = NotificationService.create_delivery(
            CreateDeliveryCommand(
                user=reminder.user,
                source_type=NotificationSourceType.REMINDER,
                source_id=reminder.id,
                channel_type=channel,
                deduplication_key=(
                    f"reminder:{reminder.id}:occurrence:{reminder.trigger_at.isoformat()}:"
                    f"channel:{channel.value}"
                ),
                subject=reminder.title,
                body=reminder.title,
                payload={"url": "/reminders", "reminder_id": str(reminder.id)},
                scheduled_at=occurred_at,
            )
        )
        if delivery.status == "pending":
            delivery = NotificationService.queue_delivery(
                delivery_id=delivery.id, occurred_at=occurred_at
            )
            NotificationDispatcher.queue_delivery_after_commit(delivery.id)
        deliveries.append(delivery)
    return deliveries


def create_briefing_deliveries(
    *, run: BriefingRun, occurred_at: datetime
) -> list[NotificationDelivery]:
    if run.status not in {"completed", "partial"}:
        return []
    deliveries: list[NotificationDelivery] = []
    for channel in NotificationService.channels_for(
        user=run.user, source_type=NotificationSourceType.BRIEFING
    ):
        delivery = NotificationService.create_delivery(
            CreateDeliveryCommand(
                user=run.user,
                source_type=NotificationSourceType.BRIEFING,
                source_id=run.id,
                channel_type=channel,
                deduplication_key=f"briefing:{run.id}:channel:{channel.value}",
                subject=f"Time Agent briefing — {run.target_date.isoformat()}",
                body=run.rendered_markdown,
                payload={
                    "url": f"/briefings?run={run.id}",
                    "briefing_run_id": str(run.id),
                    "warnings": run.warnings,
                },
                scheduled_at=occurred_at,
            )
        )
        if delivery.status == "pending":
            delivery = NotificationService.queue_delivery(
                delivery_id=delivery.id, occurred_at=occurred_at
            )
            NotificationDispatcher.queue_delivery_after_commit(delivery.id)
        deliveries.append(delivery)
    return deliveries
