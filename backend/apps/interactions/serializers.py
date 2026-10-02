from typing import Any

from rest_framework import serializers

from apps.interactions.models import (
    InteractionArtifact,
    InteractionTelemetryEventType,
    InteractionType,
)
from apps.planning.serializers import SchedulePlanSerializer

CLIENT_REPORTED_TELEMETRY_TYPES = {
    InteractionTelemetryEventType.SHOWN,
    InteractionTelemetryEventType.STARTED,
    InteractionTelemetryEventType.MEMORY_SHOWN,
    InteractionTelemetryEventType.INVALID_DROP,
    InteractionTelemetryEventType.PLAN_EDIT,
    InteractionTelemetryEventType.UNDO,
}
CLIENT_TELEMETRY_FIELDS_BY_EVENT = {
    InteractionTelemetryEventType.SHOWN: frozenset(),
    InteractionTelemetryEventType.STARTED: frozenset(),
    InteractionTelemetryEventType.MEMORY_SHOWN: frozenset(),
    InteractionTelemetryEventType.INVALID_DROP: frozenset({"drag_count", "invalid_drop_count"}),
    InteractionTelemetryEventType.PLAN_EDIT: frozenset({"plan_edit_count"}),
    InteractionTelemetryEventType.UNDO: frozenset({"undo_count"}),
}


class InteractionArtifactSerializer(serializers.ModelSerializer[InteractionArtifact]):
    conversation_id = serializers.UUIDField(allow_null=True)
    agent_run_id = serializers.UUIDField(allow_null=True)
    plan_id = serializers.UUIDField(allow_null=True)
    task_id = serializers.UUIDField(allow_null=True)

    class Meta:
        model = InteractionArtifact
        fields = [
            "id",
            "conversation_id",
            "agent_run_id",
            "plan_id",
            "plan_version",
            "task_id",
            "type",
            "payload",
            "allowed_actions",
            "status",
            "expires_at",
            "version",
            "created_at",
            "updated_at",
            "resolved_at",
        ]


class EnsureInteractionSerializer(serializers.Serializer[dict[str, Any]]):
    type = serializers.ChoiceField(source="interaction_type", choices=InteractionType.choices)
    plan_id = serializers.UUIDField(required=False)
    task_id = serializers.UUIDField(required=False)
    conversation_id = serializers.UUIDField(required=False)
    agent_run_id = serializers.UUIDField(required=False)


class InteractionSubmitSerializer(serializers.Serializer[dict[str, Any]]):
    expected_version = serializers.IntegerField(min_value=1)
    action = serializers.CharField(max_length=32)
    values = serializers.JSONField(default=dict)
    idempotency_key = serializers.CharField(max_length=128)

    def validate_values(self, value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise serializers.ValidationError("values must be an object")
        return value


class InteractionSubmissionResponseSerializer(serializers.Serializer[dict[str, Any]]):
    accepted = serializers.BooleanField()
    detail = serializers.CharField(allow_null=True)
    interaction = InteractionArtifactSerializer()
    plan = SchedulePlanSerializer(allow_null=True)
    reason_codes = serializers.ListField(child=serializers.CharField())
    conflicts = serializers.ListField(child=serializers.DictField(child=serializers.CharField()))
    candidate = serializers.DictField(child=serializers.CharField(), allow_null=True)
    replayed = serializers.BooleanField()


class InteractionTelemetrySerializer(serializers.Serializer[dict[str, Any]]):
    event_type = serializers.ChoiceField(
        choices=[
            choice
            for choice in InteractionTelemetryEventType.choices
            if choice[0] in CLIENT_REPORTED_TELEMETRY_TYPES
        ]
    )
    interaction_type = serializers.ChoiceField(choices=InteractionType.choices)
    duration_ms = serializers.IntegerField(
        min_value=0, max_value=86_400_000, required=False, allow_null=True
    )
    drag_count = serializers.IntegerField(min_value=0, max_value=1000, required=False, default=0)
    invalid_drop_count = serializers.IntegerField(
        min_value=0, max_value=1000, required=False, default=0
    )
    undo_count = serializers.IntegerField(min_value=0, max_value=1000, required=False, default=0)
    plan_edit_count = serializers.IntegerField(
        min_value=0, max_value=1000, required=False, default=0
    )
    actual_vs_planned_ratio = serializers.FloatField(
        min_value=0, max_value=10, required=False, allow_null=True
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        event_type = attrs["event_type"]
        supplied_fields = set(self.initial_data) - {"event_type", "interaction_type"}
        unsupported_fields = supplied_fields - CLIENT_TELEMETRY_FIELDS_BY_EVENT[event_type]
        if unsupported_fields:
            raise serializers.ValidationError(
                {
                    field: "This metric is not valid for the selected event type."
                    for field in sorted(unsupported_fields)
                }
            )
        return attrs
