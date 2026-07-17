import re
from typing import Any

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.reminders.models import Reminder
from apps.reminders.services import (
    CreateReminderCommand,
    ReminderIdempotencyConflictError,
    ReminderService,
)

EXPLICIT_OFFSET_PATTERN = re.compile(r"(?:Z|[+-]\d{2}:\d{2})$")


class ExplicitTimezoneDateTimeField(serializers.DateTimeField):
    def to_internal_value(self, value: Any) -> Any:
        if not isinstance(value, str) or not EXPLICIT_OFFSET_PATTERN.search(value):
            raise serializers.ValidationError("Datetime must include an explicit UTC offset")
        return super().to_internal_value(value)


class ReminderSerializer(serializers.ModelSerializer[Reminder]):
    class Meta:
        model = Reminder
        fields = [
            "id",
            "target_type",
            "target_id",
            "title",
            "trigger_at",
            "timezone",
            "channel",
            "status",
            "deduplication_key",
            "queued_at",
            "sent_at",
            "retry_count",
            "failure_reason",
            "created_at",
            "updated_at",
        ]


class CreateReminderSerializer(serializers.ModelSerializer[Reminder]):
    trigger_at = ExplicitTimezoneDateTimeField()

    class Meta:
        model = Reminder
        fields = [
            "target_type",
            "target_id",
            "title",
            "trigger_at",
            "timezone",
            "channel",
            "deduplication_key",
        ]

    def create(self, validated_data: dict[str, Any]) -> Reminder:
        user = self.context["request"].user
        if not isinstance(user, User):
            raise serializers.ValidationError("A persisted user is required")
        try:
            return ReminderService.create_reminder(
                CreateReminderCommand(user=user, **validated_data)
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        except ReminderIdempotencyConflictError as exc:
            raise serializers.ValidationError({"deduplication_key": str(exc)}) from exc
