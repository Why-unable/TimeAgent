from datetime import datetime
from typing import Any

from django.contrib.auth.models import User

from apps.planning.schemas import PlanningConstraints
from apps.planning.services import PlanningService
from apps.preferences.models import UserPreference
from common.time import to_utc


class FreeTimeRecommendationService:
    @staticmethod
    def recommend(
        *,
        user: User,
        range_start: datetime,
        range_end: datetime,
        duration_minutes: int,
        max_results: int = 8,
    ) -> dict[str, Any]:
        preference = UserPreference.objects.filter(user=user).first() or UserPreference(user=user)
        slots = PlanningService.find_free_slots(
            user=user,
            range_start=range_start,
            range_end=range_end,
            duration_minutes=duration_minutes,
            constraints=PlanningConstraints(
                timezone=preference.timezone,
                max_results=max_results,
            ),
        )
        return {
            "range_start": to_utc(range_start),
            "range_end": to_utc(range_end),
            "timezone": preference.timezone,
            "duration_minutes": duration_minutes,
            "slots": [
                {
                    "start_at": slot.start_at,
                    "end_at": slot.end_at,
                    "reason_codes": ["within_work_hours", "no_existing_overlap"],
                }
                for slot in slots
            ],
            "fallback": "no_valid_slot" if not slots else "",
        }
