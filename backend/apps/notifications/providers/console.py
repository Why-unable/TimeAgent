import logging

from apps.notifications.models import NotificationChannelType
from apps.notifications.providers.base import NotificationMessage, ProviderSendResult

logger = logging.getLogger(__name__)


class ConsoleNotificationProvider:
    channel_type = NotificationChannelType.CONSOLE

    def send(self, message: NotificationMessage) -> ProviderSendResult:
        logger.info(
            "notification_delivery provider=console delivery_id=%s user_id=%s",
            message.delivery_id,
            message.user_id,
        )
        return ProviderSendResult(
            accepted=True,
            provider_message_id=message.idempotency_key,
            provider_status="accepted",
        )
