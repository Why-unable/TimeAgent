from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.external_data.configuration import get_provider_config
from apps.preferences.models import UserPreference


class UserPreferenceSerializer(serializers.ModelSerializer[UserPreference]):
    locale = serializers.ChoiceField(choices=(("zh-CN", "简体中文"), ("en-US", "English")))
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
            "weather_location_data",
            "weather_forecast_days",
            "require_event_creation_approval",
            "require_event_cancellation_approval",
            "news_topics",
            "daily_briefing_enabled",
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

    def validate_news_topics(self, value: list[str]) -> list[str]:
        allowed = {
            topic
            for feed in get_provider_config().news.feeds
            for topic in feed.topics
        } | set(get_provider_config().news.topic_aliases)
        invalid = sorted({topic for topic in value if topic not in allowed})
        if invalid:
            raise serializers.ValidationError(f"Unsupported news topics: {', '.join(invalid)}")
        return value
