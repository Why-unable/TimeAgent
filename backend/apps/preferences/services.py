from collections.abc import Mapping
from typing import Any, cast

from django.contrib.auth.models import AbstractBaseUser, User
from django.db import transaction

from apps.accounts.services import GuestAccountPolicyService
from apps.preferences.models import UserPreference
from apps.preferences.snapshots import PlanningPreferencesSnapshot


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
            "weather_location_data",
            "weather_forecast_days",
            "require_event_creation_approval",
            "require_event_cancellation_approval",
            "news_topics",
            "daily_briefing_enabled",
            "briefing_time",
            "evening_briefing_enabled",
            "evening_briefing_time",
            "planning_rules",
            "time_memory_enabled",
            "time_memory_allow_generation",
            "time_memory_allow_context_injection",
            "proactive_insights_enabled",
            "insight_daily_notification_limit",
            "insight_cooldown_minutes",
            "disabled_insight_kinds",
        }
    )

    @staticmethod
    def get_for_user(user: User) -> UserPreference | None:
        if user.pk is None:
            raise ValueError("Preference user must be persisted")
        return UserPreference.objects.filter(user=user).first()

    @staticmethod
    def planning_snapshot_for_user(user: User) -> PlanningPreferencesSnapshot:
        preference = UserPreferenceService.get_for_user(user)
        if preference is None:
            preference = UserPreference(user=user)
        return PlanningPreferencesSnapshot.from_preference(preference)

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
        GuestAccountPolicyService.validate_preference_changes(cast(User, user), changes)

        preference, _ = UserPreference.objects.select_for_update().get_or_create(user=user)
        for field_name, value in changes.items():
            setattr(preference, field_name, value)
        preference.full_clean()
        preference.save()
        if set(changes) & {
            "timezone",
            "time_memory_enabled",
            "time_memory_allow_generation",
        }:
            from apps.time_memory.event_handler import mark_time_memory_dirty

            mark_time_memory_dirty(user=preference.user)
        return preference
