import logging

from celery import shared_task
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from apps.agents.configuration import get_agent_config
from apps.agents.memory.store import open_postgres_store
from apps.agents.model import build_chat_model
from apps.conversations.models import AgentRun, AgentRunStatus
from apps.preferences.services import UserPreferenceService
from apps.time_memory.extraction import SemanticMemoryExtractionService
from apps.time_memory.models import TimeMemoryRefreshState, TimeMemoryRefreshStatus
from apps.time_memory.semantic_projection import SemanticMemoryProjection
from apps.time_memory.settings import get_time_memory_settings
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


@shared_task(
    bind=True,
    name="time_memory.extract_semantic",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=90,
    time_limit=105,
)  # type: ignore[untyped-decorator]
def extract_semantic_memory(self: object, run_id: str) -> int:
    if not get_time_memory_settings().semantic_extraction_enabled:
        return 0
    run = AgentRun.objects.select_related("conversation__user").filter(pk=run_id).first()
    if run is None or run.status != AgentRunStatus.COMPLETED:
        return 0
    preference = UserPreferenceService.get_for_user(run.conversation.user)
    if preference is None or not preference.time_memory_allow_generation:
        return 0
    config = get_agent_config()
    model = build_chat_model(config.agent.selected_memory_extraction_model)
    proposals = SemanticMemoryExtractionService.extract_for_run(
        user=run.conversation.user, run=run, model=model
    )
    return len(proposals)


@shared_task(
    name="time_memory.rebuild_semantic_projection",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=30,
    time_limit=45,
)  # type: ignore[untyped-decorator]
def rebuild_semantic_memory_projection(user_id: str) -> int:
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        return 0
    with open_postgres_store() as store:
        return SemanticMemoryProjection.rebuild(store=store, user=user)
