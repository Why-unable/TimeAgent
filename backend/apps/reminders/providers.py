import logging
from dataclasses import dataclass
from typing import Protocol

from django.db import transaction

from apps.reminders.models import ReminderChannel

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    delivered: bool
    provider_message_id: str


class NotificationProvider(Protocol):
    def send(
        self,
        *,
        recipient: str,
        title: str,
        content: str,
        idempotency_key: str,
    ) -> DeliveryResult: ...


class ConsoleNotificationProvider:
    def send(
        self,
        *,
        recipient: str,
        title: str,
        content: str,
        idempotency_key: str,
    ) -> DeliveryResult:
        transaction.on_commit(
            lambda: logger.info(
                (
                    "Reminder delivered to console recipient=%s title=%s "
                    "content=%s idempotency_key=%s"
                ),
                recipient,
                title,
                content,
                idempotency_key,
            )
        )
        return DeliveryResult(
            delivered=True,
            provider_message_id=idempotency_key,
        )


def get_notification_provider(channel: ReminderChannel | str) -> NotificationProvider:
    normalized_channel = ReminderChannel(channel)
    if normalized_channel == ReminderChannel.CONSOLE:
        return ConsoleNotificationProvider()
    raise ValueError(f"Unsupported reminder channel: {normalized_channel}")
