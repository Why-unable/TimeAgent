from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.contrib.auth.models import User
from django.db.models import QuerySet

from apps.notifications.models import (
    NotificationChannelType,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationPreference,
    NotificationSourceType,
    WebPushSubscription,
)


@dataclass(frozen=True, slots=True)
class NotificationDeliveryQuery:
    user: User
    status: NotificationDeliveryStatus | str | None = None
    channel_type: NotificationChannelType | str | None = None
    source_type: NotificationSourceType | str | None = None
    created_after: datetime | None = None


def list_deliveries(query: NotificationDeliveryQuery) -> QuerySet[NotificationDelivery]:
    items = NotificationDelivery.objects.filter(user=query.user)
    if query.status:
        items = items.filter(status=query.status)
    if query.channel_type:
        items = items.filter(channel_type=query.channel_type)
    if query.source_type:
        items = items.filter(source_type=query.source_type)
    if query.created_after:
        items = items.filter(created_at__gte=query.created_after)
    return items


def get_delivery(*, user: User, delivery_id: UUID) -> NotificationDelivery:
    return NotificationDelivery.objects.get(user=user, pk=delivery_id)


def get_or_create_preference(user: User) -> NotificationPreference:
    preference, _ = NotificationPreference.objects.get_or_create(user=user)
    return preference


def active_push_subscriptions(user: User) -> QuerySet[WebPushSubscription]:
    return WebPushSubscription.objects.filter(user=user, enabled=True)
