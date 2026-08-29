from datetime import time
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.preferences.weather_location import validate_weather_location_data
from common.time import InvalidTimezoneError, validate_timezone


def validate_iana_timezone(value: str) -> None:
    try:
        validate_timezone(value)
    except InvalidTimezoneError as exc:
        raise ValidationError(str(exc), code="invalid_timezone") from exc


class UserPreference(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preference",
    )
    timezone = models.CharField(
        max_length=64,
        default=settings.DEFAULT_USER_TIMEZONE,
        validators=[validate_iana_timezone],
    )
    locale = models.CharField(max_length=35, default=settings.DEFAULT_USER_LOCALE)
    workday_start = models.TimeField(default=time(9, 0))
    workday_end = models.TimeField(default=time(18, 0))
    sleep_start = models.TimeField(default=time(23, 0))
    sleep_end = models.TimeField(default=time(7, 0))
    default_event_duration_minutes = models.PositiveSmallIntegerField(default=60)
    preferred_focus_periods = models.JSONField(default=list, blank=True)
    default_reminder_offsets = models.JSONField(default=list, blank=True)
    weather_location = models.CharField(max_length=255, blank=True)
    # The selected provider candidate is the authority for weather queries.
    # weather_location remains a readable compatibility label for existing users.
    weather_location_data = models.JSONField(default=dict, blank=True)
    weather_forecast_days = models.PositiveSmallIntegerField(default=3)
    require_event_creation_approval = models.BooleanField(default=False)
    require_event_cancellation_approval = models.BooleanField(default=False)
    news_topics = models.JSONField(default=list, blank=True)
    daily_briefing_enabled = models.BooleanField(default=False)
    briefing_time = models.TimeField(default=time(8, 0))
    evening_briefing_enabled = models.BooleanField(default=False)
    evening_briefing_time = models.TimeField(default=time(21, 0))
    planning_rules = models.JSONField(default=dict, blank=True)
    time_memory_enabled = models.BooleanField(default=True)
    time_memory_allow_generation = models.BooleanField(default=True)
    time_memory_allow_context_injection = models.BooleanField(default=True)
    proactive_insights_enabled = models.BooleanField(default=True)
    insight_daily_notification_limit = models.PositiveSmallIntegerField(default=3)
    insight_cooldown_minutes = models.PositiveSmallIntegerField(default=240)
    disabled_insight_kinds = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user_id"]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.timezone}"

    def clean(self) -> None:
        super().clean()
        if self.workday_start >= self.workday_end:
            raise ValidationError({"workday_end": "workday_end must be later than workday_start"})
        if not 5 <= self.default_event_duration_minutes <= 1440:
            raise ValidationError(
                {"default_event_duration_minutes": ("Duration must be between 5 and 1440 minutes")}
            )
        if not 1 <= self.weather_forecast_days <= 7:
            raise ValidationError({"weather_forecast_days": "Must be between 1 and 7 days"})
        if self.insight_daily_notification_limit > 100:
            raise ValidationError({"insight_daily_notification_limit": "Must be at most 100"})
        if self.insight_cooldown_minutes > 10080:
            raise ValidationError({"insight_cooldown_minutes": "Must be at most 10080"})
        self._validate_string_list("disabled_insight_kinds", self.disabled_insight_kinds)
        self._validate_weather_location_data()
        self._validate_integer_list("default_reminder_offsets", self.default_reminder_offsets)
        self._validate_string_list("news_topics", self.news_topics)
        if not isinstance(self.preferred_focus_periods, list):
            raise ValidationError({"preferred_focus_periods": "Must be a list"})
        if not isinstance(self.planning_rules, dict):
            raise ValidationError({"planning_rules": "Must be an object"})

    @staticmethod
    def _validate_integer_list(field_name: str, value: Any) -> None:
        if not isinstance(value, list) or any(
            not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in value
        ):
            raise ValidationError({field_name: "Must be a list of non-negative integers"})

    @staticmethod
    def _validate_string_list(field_name: str, value: Any) -> None:
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise ValidationError({field_name: "Must be a list of non-empty strings"})

    def _validate_weather_location_data(self) -> None:
        validate_weather_location_data(self.weather_location_data)
