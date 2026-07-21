from typing import Any

from rest_framework import serializers

from apps.briefings.models import BriefingDefinition, BriefingRun, BriefingSectionRun
from apps.conversations.serializers import AgentRunSerializer, ConversationSerializer


class BriefingDefinitionSerializer(serializers.ModelSerializer[BriefingDefinition]):
    class Meta:
        model = BriefingDefinition
        fields = [
            "id",
            "name",
            "enabled_sections",
            "locale",
            "timezone",
            "style",
            "include_empty_sections",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_enabled_sections(self, value: object) -> list[str]:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise serializers.ValidationError("enabled_sections must be a list of strings")
        return value


class BriefingSectionRunSerializer(serializers.ModelSerializer[BriefingSectionRun]):
    class Meta:
        model = BriefingSectionRun
        fields = [
            "id",
            "section_key",
            "status",
            "source_snapshot",
            "source_references",
            "warning",
            "error_code",
            "started_at",
            "completed_at",
        ]
        read_only_fields = fields


class BriefingRunSerializer(serializers.ModelSerializer[BriefingRun]):
    definition_id = serializers.UUIDField(read_only=True)
    conversation_id = serializers.UUIDField(read_only=True, allow_null=True)
    agent_run_id = serializers.UUIDField(read_only=True, allow_null=True)
    section_runs = BriefingSectionRunSerializer(many=True, read_only=True)

    class Meta:
        model = BriefingRun
        fields = [
            "id",
            "definition_id",
            "conversation_id",
            "agent_run_id",
            "operation_id",
            "trigger_type",
            "target_date",
            "timezone",
            "status",
            "definition_snapshot",
            "structured_result",
            "research_report",
            "rendered_markdown",
            "warnings",
            "model_config_snapshot",
            "prompt_version",
            "failure_code",
            "failure_message",
            "started_at",
            "completed_at",
            "created_at",
            "section_runs",
        ]
        read_only_fields = fields


class LaunchBriefingSerializer(serializers.Serializer[Any]):
    definition_id = serializers.UUIDField(required=False, allow_null=True)
    target_date = serializers.DateField(required=False)
    operation_id = serializers.UUIDField(required=False)


class LaunchBriefingResponseSerializer(serializers.Serializer[Any]):
    conversation = ConversationSerializer()
    agent_run = AgentRunSerializer()
