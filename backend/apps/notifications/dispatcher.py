from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

from django.conf import settings
from django.db import transaction

from apps.notifications.models import NotificationDelivery, NotificationDeliveryStatus

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    @staticmethod
    def queue_due_deliveries(
        *, now: datetime, enqueue: Callable[[UUID], object], batch_size: int = 100
    ) -> int:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        stale_before = now - timedelta(
            seconds=int(getattr(settings, "NOTIFICATION_SENDING_STALE_SECONDS", 300))
        )
        with transaction.atomic():
            stale = list(
                NotificationDelivery.objects.select_for_update(skip_locked=True)
                .filter(status=NotificationDeliveryStatus.SENDING, sending_at__lte=stale_before)
                .order_by("sending_at", "id")[:batch_size]
            )
            for delivery in stale:
                delivery.transition_to(
                    NotificationDeliveryStatus.FAILED,
                    occurred_at=now,
                    failure_code="worker_interrupted",
                    failure_reason="A worker stopped while sending; delivery recovered",
                    next_retry_at=now,
                )
                delivery.transition_to(NotificationDeliveryStatus.QUEUED, occurred_at=now)
                delivery.save()

            remaining = max(0, batch_size - len(stale))
            retryable = list(
                NotificationDelivery.objects.select_for_update(skip_locked=True)
                .filter(
                    status=NotificationDeliveryStatus.FAILED,
                    next_retry_at__lte=now,
                )
                .order_by("next_retry_at", "id")[:remaining]
            )
            for delivery in retryable:
                delivery.transition_to(NotificationDeliveryStatus.QUEUED, occurred_at=now)
                delivery.save()

            remaining = max(0, remaining - len(retryable))
            candidates = list(
                NotificationDelivery.objects.select_for_update(skip_locked=True)
                .filter(status=NotificationDeliveryStatus.PENDING, scheduled_at__lte=now)
                .order_by("scheduled_at", "id")[:remaining]
            )
            ids = [item.id for item in stale]
            ids.extend(item.id for item in retryable)
            for delivery in candidates:
                delivery.transition_to(NotificationDeliveryStatus.QUEUED, occurred_at=now)
                delivery.save()
                ids.append(delivery.id)

            remaining = max(0, batch_size - len(ids))
            already_queued = list(
                NotificationDelivery.objects.select_for_update(skip_locked=True)
                .filter(status=NotificationDeliveryStatus.QUEUED)
                .exclude(pk__in=ids)
                .order_by("queued_at", "id")[:remaining]
            )
            ids.extend(item.id for item in already_queued)

            def enqueue_all() -> None:
                for delivery_id in ids:
                    enqueue(delivery_id)

            transaction.on_commit(enqueue_all)
        return len(ids)

    @staticmethod
    def queue_delivery_after_commit(delivery_id: UUID) -> None:
        from apps.notifications.tasks import send_notification_delivery

        transaction.on_commit(
            lambda: send_notification_delivery.apply_async(args=[str(delivery_id)])
        )
