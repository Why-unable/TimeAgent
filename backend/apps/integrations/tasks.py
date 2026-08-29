import logging
from datetime import timedelta
from uuid import UUID

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.integrations.calendar.exceptions import (
    ExternalCalendarAuthenticationError,
    ExternalCalendarPermanentError,
    ExternalCalendarRateLimitError,
    ExternalCalendarTemporaryError,
)
from apps.integrations.calendar.polling import CalendarPollingService
from apps.integrations.calendar.sync_services import CalendarSyncUnavailableError
from apps.integrations.models import CalendarSyncConnection

logger = logging.getLogger(__name__)


@shared_task(name="integrations.poll_calendars")  # type: ignore[untyped-decorator]
def dispatch_calendar_polls() -> int:
    if not settings.CALENDAR_POLL_ENABLED:
        return 0
    connection_ids = CalendarPollingService.list_due_connection_ids(
        now=timezone.now(),
        minimum_interval=timedelta(seconds=settings.CALENDAR_POLL_INTERVAL_SECONDS),
        batch_size=settings.CALENDAR_POLL_BATCH_SIZE,
    )
    for connection_id in connection_ids:
        sync_calendar_connection.delay(str(connection_id))
    return len(connection_ids)


@shared_task(
    bind=True,
    name="integrations.sync_calendar",
    autoretry_for=(ExternalCalendarTemporaryError, ExternalCalendarRateLimitError),
    retry_backoff=True,
    retry_jitter=False,
    max_retries=3,
    soft_time_limit=55,
    time_limit=60,
)  # type: ignore[untyped-decorator]
def sync_calendar_connection(self: object, connection_id: str) -> bool:
    del self
    if not settings.CALENDAR_POLL_ENABLED:
        return False
    try:
        CalendarPollingService.sync_connection(
            connection_id=UUID(connection_id),
            now=timezone.now(),
            lookback=timedelta(days=settings.CALENDAR_POLL_LOOKBACK_DAYS),
            lookahead=timedelta(days=settings.CALENDAR_POLL_LOOKAHEAD_DAYS),
        )
    except CalendarSyncConnection.DoesNotExist:
        return False
    except CalendarSyncUnavailableError:
        return False
    except (ExternalCalendarAuthenticationError, ExternalCalendarPermanentError):
        logger.info("calendar_poll_not_retried connection_id=%s", connection_id)
        return False
    return True
