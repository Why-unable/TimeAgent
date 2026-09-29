from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.conversations.models import AgentEvent, AgentRun, Conversation


class ConversationSerializer(serializers.ModelSerializer[Conversation]):
    class Meta:
        model = Conversation
        fields = ["id", "title", "kind", "created_at", "updated_at"]
        read_only_fields = fields


class CreateConversationSerializer(serializers.Serializer[Any]):
    title = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class CreateMessageSerializer(serializers.Serializer[Any]):
    conversation_id = serializers.UUIDField()
    message = serializers.CharField(max_length=10000, trim_whitespace=True)
    operation_id = serializers.UUIDField(required=False)


class AgentRunSerializer(serializers.ModelSerializer[AgentRun]):
    conversation_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = AgentRun
        fields = [
            "id",
            "conversation_id",
            "operation_id",
            "request_id",
            "trigger_type",
            "trigger_payload",
            "synthetic_input",
            "status",
            "input_message",
            "anchor_at",
            "anchor_timezone",
            "final_response",
            "error",
            "started_at",
            "completed_at",
            "created_at",
        ]
        read_only_fields = fields


class SchedulePlanArtifactReferenceSerializer(serializers.Serializer[dict[str, Any]]):
    artifact_type = serializers.ChoiceField(choices=["schedule_plan"])
    artifact_id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=1)


class ConversationAgentRunSerializer(AgentRunSerializer):
    artifacts = serializers.SerializerMethodField()

    class Meta(AgentRunSerializer.Meta):
        fields = [*AgentRunSerializer.Meta.fields, "artifacts"]

    @extend_schema_field(SchedulePlanArtifactReferenceSerializer(many=True))
    def get_artifacts(self, run: AgentRun) -> list[dict[str, object]]:
        references: dict[str, dict[str, object]] = {}
        for event in run.events.all():
            payload = event.payload
            if (
                event.event_type != "artifact.available"
                or not isinstance(payload, dict)
                or payload.get("artifact_type") != "schedule_plan"
                or not isinstance(payload.get("artifact_id"), str)
                or not isinstance(payload.get("version"), int)
                or isinstance(payload.get("version"), bool)
            ):
                continue
            reference = SchedulePlanArtifactReferenceSerializer(data=payload)
            if reference.is_valid():
                artifact = reference.validated_data
                references[str(artifact["artifact_id"])] = artifact
        return list(references.values())


class ConversationDetailSerializer(serializers.ModelSerializer[Conversation]):
    runs = ConversationAgentRunSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = ["id", "title", "kind", "created_at", "updated_at", "runs"]
        read_only_fields = fields


class AgentEventSerializer(serializers.ModelSerializer[AgentEvent]):
    class Meta:
        model = AgentEvent
        fields = ["sequence", "event_type", "payload", "created_at"]
        read_only_fields = fields
