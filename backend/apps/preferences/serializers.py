from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.preferences.models import UserPreference


class UserPreferenceSerializer(serializers.ModelSerializer[UserPreference]):
    class Meta:
        model = UserPreference
        fields = [
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
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance = self.instance or UserPreference()
        for field_name, value in attrs.items():
            setattr(instance, field_name, value)
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        return attrs
