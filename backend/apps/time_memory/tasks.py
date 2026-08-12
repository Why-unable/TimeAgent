import logging

from celery import shared_task
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from apps.agents.memory.store import open_postgres_store
from apps.time_memory.models import TimeMemoryRefreshState, TimeMemoryRefreshStatus
from apps.time_memory.updater import TimeMemoryUpdater

logger = logging.getLogger(__name__)


@shared_task(name="time_memory.rebuild")  # type: ignore[untyped-decorator]
def rebuild_time_memory(user_id: str, expected_dirty_at: str | None = None) -> bool:
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        return False
    try:
        with transaction.atomic():
            state, _ = TimeMemoryRefreshState.objects.select_for_update().get_or_create(user=user)
            if state.status != TimeMemoryRefreshStatus.DIRTY:
                return False
            state.status = TimeMemoryRefreshStatus.PROCESSING
            state.last_started_at = timezone.now()
            state.save(update_fields=["status", "last_started_at", "updated_at"])
            with open_postgres_store() as store:
                TimeMemoryUpdater.rebuild(user=user, store=store)
    except Exception as exc:
        TimeMemoryUpdater.mark_failed(user=user, error=exc)
        logger.exception("time_memory_rebuild_failed user_id=%s", user_id)
        raise
    return True


@shared_task(name="time_memory.refresh_daily")  # type: ignore[untyped-decorator]
def refresh_daily_time_memories() -> int:
    queued = 0
    users = get_user_model().objects.filter(
        preference__time_memory_enabled=True,
        preference__time_memory_allow_generation=True,
    )
    for user in users.iterator():
        assert isinstance(user, User)
        state, _ = TimeMemoryRefreshState.objects.get_or_create(user=user)
        state.status = TimeMemoryRefreshStatus.DIRTY
        state.dirty_at = timezone.now()
        state.save(update_fields=["status", "dirty_at", "updated_at"])
        rebuild_time_memory.delay(str(user.pk), state.dirty_at.isoformat())
        queued += 1
    return queued
