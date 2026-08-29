from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.services import GuestAccountPolicyService
from apps.notifications.models import (
    NotificationChannelType,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationPreference,
    NotificationSourceType,
    WebPushSubscription,
)
from apps.notifications.providers.base import NotificationMessage, WebPushTarget
from apps.notifications.selectors import active_push_subscriptions, get_or_create_preference


class NotificationIdempotencyConflictError(ValueError):
    pass


class NotificationDeliveryUnavailableError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CreateDeliveryCommand:
    user: User
    source_type: NotificationSourceType | str
    source_id: UUID | None
    channel_type: NotificationChannelType | str
    deduplication_key: str
    subject: str
    body: str
    scheduled_at: datetime
    payload: dict[str, object]


class NotificationService:
    @staticmethod
    @transaction.atomic
    def create_delivery(command: CreateDeliveryCommand) -> NotificationDelivery:
        if command.user.pk is None:
            raise ValueError("Notification user must be persisted")
        candidate = NotificationDelivery(
            user=command.user,
            source_type=command.source_type,
            source_id=command.source_id,
            channel_type=command.channel_type,
            deduplication_key=command.deduplication_key,
            subject=command.subject,
            body=command.body,
            payload=command.payload,
            scheduled_at=command.scheduled_at,
        )
        candidate.full_clean(validate_constraints=False)
        existing = NotificationDelivery.objects.filter(
            user=command.user, deduplication_key=candidate.deduplication_key
        ).first()
        if existing is not None:
            NotificationService._ensure_same(existing, candidate)
            return existing
        try:
            with transaction.atomic():
                candidate.save(force_insert=True)
        except IntegrityError:
            existing = NotificationDelivery.objects.get(
                user=command.user, deduplication_key=candidate.deduplication_key
            )
            NotificationService._ensure_same(existing, candidate)
            return existing
        return candidate

    @staticmethod
    @transaction.atomic
    def queue_delivery(*, delivery_id: UUID, occurred_at: datetime) -> NotificationDelivery:
        delivery = NotificationDelivery.objects.select_for_update().get(pk=delivery_id)
        if delivery.status == NotificationDeliveryStatus.QUEUED:
            return delivery
        if delivery.status in {
            NotificationDeliveryStatus.SENT,
            NotificationDeliveryStatus.CANCELLED,
        }:
            raise NotificationDeliveryUnavailableError(
                f"Delivery in {delivery.status} status cannot be queued"
            )
        delivery.transition_to(NotificationDeliveryStatus.QUEUED, occurred_at=occurred_at)
        delivery.full_clean()
        delivery.save()
        return delivery

    @staticmethod
    @transaction.atomic
    def cancel_delivery(
        *, delivery_id: UUID, user: User, occurred_at: datetime
    ) -> NotificationDelivery:
        delivery = NotificationDelivery.objects.select_for_update().get(pk=delivery_id, user=user)
        if delivery.status == NotificationDeliveryStatus.CANCELLED:
            return delivery
        delivery.transition_to(NotificationDeliveryStatus.CANCELLED, occurred_at=occurred_at)
        delivery.save()
        return delivery

    @staticmethod
    @transaction.atomic
    def cancel_source_deliveries(
        *,
        user: User,
        source_type: NotificationSourceType | str,
        source_ids: list[UUID],
        occurred_at: datetime,
    ) -> int:
        """Cancel every delivery for source facts that has not started sending."""
        if not source_ids:
            return 0
        deliveries = NotificationDelivery.objects.select_for_update().filter(
            user=user,
            source_type=source_type,
            source_id__in=source_ids,
            status__in=[
                NotificationDeliveryStatus.PENDING,
                NotificationDeliveryStatus.QUEUED,
                NotificationDeliveryStatus.FAILED,
            ],
        )
        cancelled = 0
        for delivery in deliveries:
            delivery.transition_to(NotificationDeliveryStatus.CANCELLED, occurred_at=occurred_at)
            delivery.save(update_fields=["status", "updated_at"])
            cancelled += 1
        return cancelled

    @staticmethod
    @transaction.atomic
    def mark_sending(*, delivery_id: UUID, occurred_at: datetime) -> NotificationDelivery | None:
        delivery = (
            NotificationDelivery.objects.select_for_update()
            .select_related("user")
            .filter(pk=delivery_id)
            .first()
        )
        if delivery is None:
            raise NotificationDelivery.DoesNotExist
        if delivery.status in {
            NotificationDeliveryStatus.SENDING,
            NotificationDeliveryStatus.SENT,
            NotificationDeliveryStatus.CANCELLED,
            NotificationDeliveryStatus.PENDING,
            NotificationDeliveryStatus.FAILED,
        }:
            return None
        delivery.transition_to(NotificationDeliveryStatus.SENDING, occurred_at=occurred_at)
        delivery.save()
        return delivery

    @staticmethod
    @transaction.atomic
    def mark_sent(
        *, delivery_id: UUID, occurred_at: datetime, provider_message_id: str
    ) -> NotificationDelivery:
        delivery = NotificationDelivery.objects.select_for_update().get(pk=delivery_id)
        delivery.transition_to(
            NotificationDeliveryStatus.SENT,
            occurred_at=occurred_at,
            provider_message_id=provider_message_id,
        )
        delivery.full_clean()
        delivery.save()
        return delivery

    @staticmethod
    @transaction.atomic
    def mark_failed(
        *,
        delivery_id: UUID,
        occurred_at: datetime,
        failure_code: str,
        failure_reason: str,
        next_retry_at: datetime | None = None,
    ) -> NotificationDelivery:
        delivery = NotificationDelivery.objects.select_for_update().get(pk=delivery_id)
        delivery.transition_to(
            NotificationDeliveryStatus.FAILED,
            occurred_at=occurred_at,
            failure_code=failure_code,
            failure_reason=failure_reason,
            next_retry_at=next_retry_at,
        )
        delivery.full_clean()
        delivery.save()
        return delivery

    @staticmethod
    def retry_delivery(*, delivery_id: UUID, occurred_at: datetime) -> NotificationDelivery:
        return NotificationService.queue_delivery(delivery_id=delivery_id, occurred_at=occurred_at)

    @staticmethod
    def build_message(delivery: NotificationDelivery) -> NotificationMessage:
        subscriptions = active_push_subscriptions(delivery.user)
        return NotificationMessage(
            delivery_id=str(delivery.pk),
            user_id=str(delivery.user_id),
            subject=delivery.subject,
            body=delivery.body,
            payload=delivery.payload,
            idempotency_key=delivery.deduplication_key,
            recipient_email=delivery.user.email,
            web_push_targets=tuple(
                WebPushTarget(
                    subscription_id=str(item.pk),
                    endpoint=item.endpoint,
                    p256dh=item.p256dh,
                    auth=item.auth,
                )
                for item in subscriptions
            ),
        )

    @staticmethod
    @transaction.atomic
    def invalidate_push_subscriptions(*, subscription_ids: tuple[str, ...]) -> None:
        if not subscription_ids:
            return
        WebPushSubscription.objects.filter(pk__in=subscription_ids).update(
            enabled=False,
            invalidated_at=timezone.now(),
            updated_at=timezone.now(),
        )

    @staticmethod
    @transaction.atomic
    def touch_push_subscriptions(*, subscription_ids: tuple[str, ...]) -> None:
        if not subscription_ids:
            return
        WebPushSubscription.objects.filter(pk__in=subscription_ids, enabled=True).update(
            last_used_at=timezone.now(),
            updated_at=timezone.now(),
        )

    @staticmethod
    def channels_for(
        *, user: User, source_type: NotificationSourceType
    ) -> tuple[NotificationChannelType, ...]:
        preference = get_or_create_preference(user)
        prefix = "reminder" if source_type == NotificationSourceType.REMINDER else "briefing"
        channels = []
        for channel, suffix in (
            (NotificationChannelType.CONSOLE, "console_enabled"),
            (NotificationChannelType.EMAIL, "email_enabled"),
            (NotificationChannelType.WEB_PUSH, "web_push_enabled"),
        ):
            if getattr(preference, f"{prefix}_{suffix}"):
                channels.append(channel)
        return tuple(channels)

    @staticmethod
    def get_or_create_preference(user: User) -> NotificationPreference:
        return get_or_create_preference(user)

    @staticmethod
    @transaction.atomic
    def update_preference(user: User, data: dict[str, bool]) -> NotificationPreference:
        allowed = {
            "reminder_console_enabled",
            "reminder_email_enabled",
            "reminder_web_push_enabled",
            "briefing_console_enabled",
            "briefing_email_enabled",
            "briefing_web_push_enabled",
        }
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(f"Unsupported notification preference fields: {', '.join(unknown)}")
        GuestAccountPolicyService.validate_notification_changes(user, data)
        preference = get_or_create_preference(user)
        for field, value in data.items():
            if not isinstance(value, bool):
                raise ValidationError({field: "Must be a boolean"})
            setattr(preference, field, value)
        preference.full_clean()
        preference.save()
        return preference

    @staticmethod
    @transaction.atomic
    def save_push_subscription(
        *, user: User, endpoint: str, p256dh: str, auth: str, user_agent: str
    ) -> WebPushSubscription:
        GuestAccountPolicyService.assert_push_allowed(user)
        existing = WebPushSubscription.objects.select_for_update().filter(endpoint=endpoint).first()
        if existing is not None and existing.user_id != user.pk:
            raise PermissionError("Push subscription belongs to another user")
        subscription = existing or WebPushSubscription(user=user, endpoint=endpoint)
        subscription.p256dh = p256dh
        subscription.auth = auth
        subscription.user_agent = user_agent[:512]
        subscription.enabled = True
        subscription.invalidated_at = None
        subscription.full_clean()
        subscription.save()
        return subscription

    @staticmethod
    @transaction.atomic
    def delete_push_subscription(*, user: User, subscription_id: UUID) -> None:
        subscription = WebPushSubscription.objects.select_for_update().get(
            pk=subscription_id, user=user
        )
        subscription.delete()

    @staticmethod
    @transaction.atomic
    def unsubscribe_push_endpoint(*, user: User, endpoint: str) -> None:
        WebPushSubscription.objects.select_for_update().filter(
            user=user,
            endpoint=endpoint.strip(),
        ).delete()

    @staticmethod
    def _ensure_same(existing: NotificationDelivery, candidate: NotificationDelivery) -> None:
        fields = (
            "source_type",
            "source_id",
            "channel_type",
            "subject",
            "body",
            "payload",
            "scheduled_at",
        )
        mismatches = [
            name for name in fields if getattr(existing, name) != getattr(candidate, name)
        ]
        if mismatches:
            raise NotificationIdempotencyConflictError(
                "Idempotency key already exists with different delivery data: "
                + ", ".join(mismatches)
            )
