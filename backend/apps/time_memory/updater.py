from datetime import UTC, datetime, timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from langgraph.store.base import BaseStore

from apps.preferences.services import UserPreferenceService
from apps.time_memory.analyzer import TimeMemoryAnalyzer
from apps.time_memory.models import (
    TimeMemoryExclusion,
    TimeMemoryExclusionType,
    TimeMemoryRefreshState,
    TimeMemoryRefreshStatus,
)
from apps.time_memory.repository import TimeMemoryRepository
from apps.time_memory.schemas import TimeMemoryProfile
from apps.time_memory.settings import get_time_memory_settings
from apps.time_memory.source_repository import TimeMemorySourceRepository


class TimeMemoryUpdater:
    @staticmethod
    def rebuild(
        *,
        user: User,
        store: BaseStore,
        now: datetime | None = None,
    ) -> TimeMemoryProfile | None:
        preference = UserPreferenceService.get_or_create_for_user(user)
        if not preference.time_memory_enabled or not preference.time_memory_allow_generation:
            TimeMemoryRepository.delete(store, user_id=str(user.pk))
            TimeMemoryRefreshState.objects.update_or_create(
                user=user,
                defaults={
                    "status": TimeMemoryRefreshStatus.CLEAN,
                    "dirty_at": None,
                    "last_completed_at": timezone.now(),
                    "last_error": "",
                },
            )
            return None

        config = get_time_memory_settings()
        current = (now or timezone.now()).astimezone(UTC)
        state, _ = TimeMemoryRefreshState.objects.update_or_create(
            user=user,
            defaults={
                "status": TimeMemoryRefreshStatus.PROCESSING,
                "last_started_at": current,
                "last_error": "",
            },
        )
        previous = TimeMemoryRepository.get(store, user_id=str(user.pk))
        history_start = current - timedelta(days=config.history_days + 1)
        if state.reset_at is not None:
            history_start = max(history_start, state.reset_at)
        source = TimeMemorySourceRepository.load(
            user=user,
            since=history_start,
            until=current,
        )
        profile = TimeMemoryAnalyzer(config).build_profile(
            user_id=str(user.pk),
            timezone_name=preference.timezone,
            now=current,
            source=source,
            previous=previous,
        )
        exclusions = TimeMemoryExclusion.objects.filter(user=user)
        excluded_places = {
            item.key for item in exclusions if item.exclusion_type == TimeMemoryExclusionType.PLACE
        }
        excluded_patterns = {
            item.key
            for item in exclusions
            if item.exclusion_type == TimeMemoryExclusionType.PATTERN
        }
        profile = profile.model_copy(
            update={
                "common_places": [
                    place
                    for place in profile.common_places
                    if place.place_id not in excluded_places
                ],
                "stable_patterns": [
                    pattern
                    for pattern in profile.stable_patterns
                    if pattern.pattern_id not in excluded_patterns
                ],
            }
        )
        TimeMemoryRepository.put(store, profile)
        TimeMemoryRefreshState.objects.filter(
            Q(dirty_at__isnull=True) | Q(dirty_at__lte=current),
            user=user,
        ).update(
            status=TimeMemoryRefreshStatus.CLEAN,
            dirty_at=None,
            last_completed_at=current,
            last_error="",
        )
        return profile

    @staticmethod
    @transaction.atomic
    def mark_failed(*, user: User, error: Exception) -> None:
        TimeMemoryRefreshState.objects.update_or_create(
            user=user,
            defaults={
                "status": TimeMemoryRefreshStatus.FAILED,
                "last_error": f"{type(error).__name__}: {error}"[:2000],
            },
        )
