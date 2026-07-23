from __future__ import annotations

import logging
import os
from datetime import timedelta
from time import monotonic
from typing import Any
from uuid import UUID

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.notifications.dispatcher import NotificationDispatcher
from apps.notifications.exceptions import PermanentNotificationError, TransientNotificationError
from apps.notifications.providers.registry import build_default_registry
from apps.notifications.services import NotificationService

logger = logging.getLogger(__name__)


@shared_task(name="notifications.dispatch_due")  # type: ignore[untyped-decorator]
def dispatch_due_notification_deliveries(batch_size: int = 100) -> int:
    return NotificationDispatcher.queue_due_deliveries(
        now=timezone.now(),
        batch_size=batch_size,
        enqueue=lambda delivery_id: send_notification_delivery.delay(str(delivery_id)),
    )


@shared_task(bind=True, name="notifications.send", soft_time_limit=25, time_limit=30)  # type: ignore[untyped-decorator]
def send_notification_delivery(self: Any, delivery_id: str) -> bool:
    parsed_id = UUID(delivery_id)
    now = timezone.now()
    delivery = NotificationService.mark_sending(delivery_id=parsed_id, occurred_at=now)
    if delivery is None:
        return False
    started = monotonic()
    provider = build_default_registry().get(delivery.channel_type)
    message = NotificationService.build_message(delivery)
    try:
        result = provider.send(message)
        if not result.accepted:
            raise TransientNotificationError("Provider did not accept the notification")
    except TransientNotificationError as exc:
        max_retries = int(getattr(settings, "NOTIFICATION_MAX_RETRIES", 4))
        retry_index = delivery.attempt_count
        can_retry = retry_index <= max_retries
        countdown = _retry_delay(retry_index) if can_retry else 0
        next_retry_at = now + timedelta(seconds=countdown) if can_retry else None
        NotificationService.mark_failed(
            delivery_id=parsed_id,
            occurred_at=timezone.now(),
            failure_code=exc.code,
            failure_reason=str(exc) or type(exc).__name__,
            next_retry_at=next_retry_at,
        )
        _log_result(delivery, "failed", started, exc.code)
        if can_retry:
            NotificationService.retry_delivery(delivery_id=parsed_id, occurred_at=timezone.now())
            raise self.retry(exc=exc, countdown=countdown, max_retries=max_retries) from exc
        return False
    except PermanentNotificationError as exc:
        NotificationService.mark_failed(
            delivery_id=parsed_id,
            occurred_at=timezone.now(),
            failure_code=exc.code,
            failure_reason=str(exc) or type(exc).__name__,
        )
        _log_result(delivery, "failed", started, exc.code)
        return False
    except Exception as exc:
        NotificationService.mark_failed(
            delivery_id=parsed_id,
            occurred_at=timezone.now(),
            failure_code="unexpected_provider_error",
            failure_reason=type(exc).__name__,
        )
        _log_result(delivery, "failed", started, "unexpected_provider_error")
        raise

    NotificationService.invalidate_push_subscriptions(
        subscription_ids=result.invalid_subscription_ids
    )
    NotificationService.touch_push_subscriptions(subscription_ids=result.accepted_subscription_ids)
    NotificationService.mark_sent(
        delivery_id=parsed_id,
        occurred_at=timezone.now(),
        provider_message_id=result.provider_message_id,
    )
    _log_result(delivery, "sent", started, "")
    return True


def _retry_delay(attempt_count: int) -> int:
    base = min(300, 1 << max(1, attempt_count))
    jitter_limit = max(2, base // 4 + 1)
    jitter = int.from_bytes(os.urandom(2), byteorder="big") % jitter_limit
    return base + jitter


def _log_result(delivery: Any, status: str, started: float, failure_code: str) -> None:
    logger.info(
        (
            "notification_delivery delivery_id=%s user_id=%s source_type=%s source_id=%s "
            "channel_type=%s status=%s attempt_count=%s provider=%s latency_ms=%s "
            "failure_code=%s"
        ),
        delivery.pk,
        delivery.user_id,
        delivery.source_type,
        delivery.source_id,
        delivery.channel_type,
        status,
        delivery.attempt_count,
        delivery.channel_type,
        round((monotonic() - started) * 1000),
        failure_code,
    )
