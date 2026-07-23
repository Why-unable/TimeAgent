from apps.notifications.exceptions import NotificationProviderNotRegisteredError
from apps.notifications.models import NotificationChannelType
from apps.notifications.providers.base import NotificationProvider


class NotificationProviderRegistry:
    def __init__(self, providers: tuple[NotificationProvider, ...] = ()) -> None:
        self._providers: dict[NotificationChannelType, NotificationProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: NotificationProvider) -> None:
        self._providers[NotificationChannelType(provider.channel_type)] = provider

    def get(self, channel_type: NotificationChannelType | str) -> NotificationProvider:
        channel = NotificationChannelType(channel_type)
        try:
            return self._providers[channel]
        except KeyError as exc:
            raise NotificationProviderNotRegisteredError(
                f"No notification provider is registered for {channel.value}"
            ) from exc


def build_default_registry() -> NotificationProviderRegistry:
    from apps.notifications.providers.console import ConsoleNotificationProvider
    from apps.notifications.providers.email import EmailNotificationProvider
    from apps.notifications.providers.web_push import WebPushNotificationProvider

    return NotificationProviderRegistry(
        (
            ConsoleNotificationProvider(),
            EmailNotificationProvider(),
            WebPushNotificationProvider(),
        )
    )
