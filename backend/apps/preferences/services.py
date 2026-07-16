from collections.abc import Mapping
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from apps.preferences.models import UserPreference


class UserPreferenceService:
    UPDATE_FIELDS = frozenset(
        {
            "timezone",
            "locale",
            "workday_start",
            "workday_end",
            "sleep_start",
            "sleep_end",
            "default_event_duration_minutes",
            "preferred_focus_periods",
            "default_reminder_offsets",
            "weather_location",
            "news_topics",
            "briefing_time",
            "planning_rules",
        }
    )

    @staticmethod
    @transaction.atomic
    def get_or_create_for_user(user: AbstractBaseUser) -> UserPreference:
        preference, _ = UserPreference.objects.get_or_create(user=user)
        return preference

    @staticmethod
    @transaction.atomic
    def update_for_user(
        user: AbstractBaseUser,
        changes: Mapping[str, Any],
    ) -> UserPreference:
        unsupported_fields = set(changes) - UserPreferenceService.UPDATE_FIELDS
        if unsupported_fields:
            fields = ", ".join(sorted(unsupported_fields))
            raise ValueError(f"Unsupported preference fields: {fields}")

        preference, _ = UserPreference.objects.select_for_update().get_or_create(user=user)
        for field_name, value in changes.items():
            setattr(preference, field_name, value)
        preference.full_clean()
        preference.save()
        return preference
