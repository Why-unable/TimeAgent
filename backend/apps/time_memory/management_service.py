from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from langgraph.store.base import BaseStore

from apps.time_memory.models import (
    TimeMemoryExclusion,
    TimeMemoryExclusionType,
    TimeMemoryRefreshState,
    TimeMemoryRefreshStatus,
)
from apps.time_memory.repository import TimeMemoryRepository
from apps.time_memory.schemas import TimeMemoryProfile


class TimeMemoryManagementService:
    @staticmethod
    def get_profile(*, user: User, store: BaseStore) -> TimeMemoryProfile | None:
        return TimeMemoryRepository.get(store, user_id=str(user.pk))

    @staticmethod
    @transaction.atomic
    def clear_profile(*, user: User, store: BaseStore) -> None:
        TimeMemoryRepository.delete(store, user_id=str(user.pk))
        TimeMemoryExclusion.objects.filter(user=user).delete()
        TimeMemoryRefreshState.objects.update_or_create(
            user=user,
            defaults={
                "status": TimeMemoryRefreshStatus.CLEAN,
                "dirty_at": None,
                "reset_at": timezone.now(),
                "last_error": "",
            },
        )

    @staticmethod
    @transaction.atomic
    def exclude_place(*, user: User, store: BaseStore, place_id: str) -> bool:
        profile = TimeMemoryRepository.get(store, user_id=str(user.pk))
        if profile is None or not any(
            place.place_id == place_id for place in profile.common_places
        ):
            return False
        TimeMemoryExclusion.objects.get_or_create(
            user=user,
            exclusion_type=TimeMemoryExclusionType.PLACE,
            key=place_id,
        )
        TimeMemoryRepository.put(
            store,
            profile.model_copy(
                update={
                    "common_places": [
                        place for place in profile.common_places if place.place_id != place_id
                    ]
                }
            ),
        )
        return True

    @staticmethod
    @transaction.atomic
    def exclude_pattern(*, user: User, store: BaseStore, pattern_id: str) -> bool:
        profile = TimeMemoryRepository.get(store, user_id=str(user.pk))
        if profile is None or not any(
            pattern.pattern_id == pattern_id for pattern in profile.stable_patterns
        ):
            return False
        TimeMemoryExclusion.objects.get_or_create(
            user=user,
            exclusion_type=TimeMemoryExclusionType.PATTERN,
            key=pattern_id,
        )
        TimeMemoryRepository.put(
            store,
            profile.model_copy(
                update={
                    "stable_patterns": [
                        pattern
                        for pattern in profile.stable_patterns
                        if pattern.pattern_id != pattern_id
                    ]
                }
            ),
        )
        return True
