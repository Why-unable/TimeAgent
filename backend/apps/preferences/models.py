from datetime import time
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

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
    news_topics = models.JSONField(default=list, blank=True)
    briefing_time = models.TimeField(default=time(8, 0))
    planning_rules = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user_id"]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.timezone}"

    def clean(self) -> None:
        super().clean()
        if self.workday_start >= self.workday_end:
            raise ValidationError(
                {"workday_end": "workday_end must be later than workday_start"}
            )
        if not 5 <= self.default_event_duration_minutes <= 1440:
            raise ValidationError(
                {
                    "default_event_duration_minutes": (
                        "Duration must be between 5 and 1440 minutes"
                    )
                }
            )
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
