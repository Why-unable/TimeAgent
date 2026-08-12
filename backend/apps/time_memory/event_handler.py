import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from django.contrib.auth.models import AbstractBaseUser, User
from django.db import transaction
from django.utils import timezone

from apps.time_memory.models import (
    MemoryEntityType,
    MemoryOperation,
    MemoryOperationSource,
    ScheduleChange,
    TimeMemoryRefreshState,
    TimeMemoryRefreshStatus,
)
from apps.time_memory.settings import get_time_memory_settings

logger = logging.getLogger(__name__)


def json_snapshot(instance: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for field_name in fields:
        value = getattr(instance, field_name)
        if isinstance(value, datetime):
            snapshot[field_name] = value.astimezone(UTC).isoformat()
        elif isinstance(value, UUID):
            snapshot[field_name] = str(value)
        else:
            snapshot[field_name] = value
    return snapshot


def record_schedule_change(
    *,
    user: User,
    entity_type: MemoryEntityType | str,
    entity_id: UUID,
    operation: MemoryOperation | str,
    source: MemoryOperationSource | str,
    old_snapshot: dict[str, Any] | None = None,
    new_snapshot: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> ScheduleChange:
    timestamp = (occurred_at or timezone.now()).astimezone(UTC)
    change = ScheduleChange.objects.create(
        user=user,
        entity_type=entity_type,
        entity_id=entity_id,
        operation=operation,
        source=source,
        old_snapshot=old_snapshot or {},
        new_snapshot=new_snapshot or {},
        occurred_at=timestamp,
    )
    _mark_dirty_and_enqueue(user=user, timestamp=timestamp)
    return change


def mark_time_memory_dirty(
    *,
    user: AbstractBaseUser,
    occurred_at: datetime | None = None,
) -> None:
    timestamp = (occurred_at or timezone.now()).astimezone(UTC)
    _mark_dirty_and_enqueue(user=user, timestamp=timestamp)


def _mark_dirty_and_enqueue(*, user: AbstractBaseUser, timestamp: datetime) -> None:
    with transaction.atomic():
        refresh_state, created = TimeMemoryRefreshState.objects.select_for_update().get_or_create(
            user=user,
            defaults={
                "status": TimeMemoryRefreshStatus.DIRTY,
                "dirty_at": timestamp,
                "last_error": "",
            },
        )
        should_enqueue = created or refresh_state.status != TimeMemoryRefreshStatus.DIRTY
        if not created:
            refresh_state.status = TimeMemoryRefreshStatus.DIRTY
            refresh_state.dirty_at = timestamp
            refresh_state.last_error = ""
            refresh_state.save(update_fields=["status", "dirty_at", "last_error", "updated_at"])

    def enqueue() -> None:
        from apps.time_memory.tasks import rebuild_time_memory

        config = get_time_memory_settings()
        if not config.auto_refresh_enabled:
            return
        try:
            rebuild_time_memory.apply_async(
                args=[str(user.pk)],
                countdown=config.refresh_delay_seconds,
            )
        except Exception:
            logger.exception("time_memory_enqueue_failed user_id=%s", user.pk)

    if should_enqueue:
        transaction.on_commit(enqueue)
