from typing import Any

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.events.models import (
    CalendarEvent,
    CalendarEventStatus,
    CalendarEventVisibility,
)
from apps.events.services import CreateEventCommand, EventService, UpdateEventCommand
from common.serializers import ExplicitTimezoneDateTimeField, StrictSerializer


class CalendarEventSerializer(serializers.ModelSerializer[CalendarEvent]):
    class Meta:
        model = CalendarEvent
        fields = [
            "id",
            "title",
            "description",
            "start_at",
            "end_at",
            "timezone",
            "location",
            "status",
            "visibility",
            "recurrence_rule",
            "source",
            "external_id",
            "created_by",
            "version",
            "created_at",
            "updated_at",
        ]


class CreateCalendarEventSerializer(StrictSerializer):
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    start_at = ExplicitTimezoneDateTimeField()
    end_at = ExplicitTimezoneDateTimeField()
    timezone = serializers.CharField(max_length=64)
    location = serializers.CharField(required=False, allow_blank=True, max_length=255)
    status = serializers.ChoiceField(
        choices=CalendarEventStatus.choices,
        required=False,
    )
    visibility = serializers.ChoiceField(
        choices=CalendarEventVisibility.choices,
        required=False,
    )
    recurrence_rule = serializers.CharField(required=False, allow_blank=True)
    source = serializers.CharField(  # type: ignore[assignment]
        required=False,
        max_length=64,
    )
    external_id = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
    )

    def create(self, validated_data: dict[str, Any]) -> CalendarEvent:
        user = self.context["request"].user
        if not isinstance(user, User):
            raise serializers.ValidationError("A persisted user is required")
        try:
            return EventService.create_event(CreateEventCommand(user=user, **validated_data))
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc


class UpdateCalendarEventSerializer(StrictSerializer):
    title = serializers.CharField(required=False, max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    start_at = ExplicitTimezoneDateTimeField(required=False)
    end_at = ExplicitTimezoneDateTimeField(required=False)
    timezone = serializers.CharField(required=False, max_length=64)
    location = serializers.CharField(required=False, allow_blank=True, max_length=255)
    status = serializers.ChoiceField(required=False, choices=CalendarEventStatus.choices)
    visibility = serializers.ChoiceField(
        required=False,
        choices=CalendarEventVisibility.choices,
    )
    recurrence_rule = serializers.CharField(required=False, allow_blank=True)
    source = serializers.CharField(required=False, max_length=64)  # type: ignore[assignment]
    external_id = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def update(
        self,
        instance: CalendarEvent,
        validated_data: dict[str, Any],
    ) -> CalendarEvent:
        expected_version = self.context["expected_version"]
        user = self.context["request"].user
        if not isinstance(user, User):
            raise serializers.ValidationError("A persisted user is required")
        try:
            return EventService.update_event(
                UpdateEventCommand(
                    user=user,
                    event_id=instance.id,
                    expected_version=expected_version,
                    changes=validated_data,
                )
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        if not attrs:
            raise serializers.ValidationError("At least one event field is required")
        return attrs


class EventListQuerySerializer(StrictSerializer):
    starts_before = ExplicitTimezoneDateTimeField(required=False)
    ends_after = ExplicitTimezoneDateTimeField(required=False)
    status = serializers.MultipleChoiceField(
        required=False,
        choices=CalendarEventStatus.choices,
    )
