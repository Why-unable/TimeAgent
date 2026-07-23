from dataclasses import dataclass, field
from typing import Protocol

from apps.notifications.models import NotificationChannelType


@dataclass(frozen=True, slots=True)
class WebPushTarget:
    subscription_id: str
    endpoint: str
    p256dh: str
    auth: str


@dataclass(frozen=True, slots=True)
class NotificationMessage:
    delivery_id: str
    user_id: str
    subject: str
    body: str
    payload: dict[str, object]
    idempotency_key: str
    recipient_email: str = ""
    web_push_targets: tuple[WebPushTarget, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderSendResult:
    accepted: bool
    provider_message_id: str
    provider_status: str
    accepted_subscription_ids: tuple[str, ...] = field(default_factory=tuple)
    invalid_subscription_ids: tuple[str, ...] = field(default_factory=tuple)


class NotificationProvider(Protocol):
    channel_type: NotificationChannelType

    def send(self, message: NotificationMessage) -> ProviderSendResult: ...
