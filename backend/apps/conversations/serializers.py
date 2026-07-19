from typing import Any

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
            "final_response",
            "error",
            "started_at",
            "completed_at",
            "created_at",
        ]
        read_only_fields = fields


class ConversationDetailSerializer(serializers.ModelSerializer[Conversation]):
    runs = AgentRunSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = ["id", "title", "kind", "created_at", "updated_at", "runs"]
        read_only_fields = fields


class AgentEventSerializer(serializers.ModelSerializer[AgentEvent]):
    class Meta:
        model = AgentEvent
        fields = ["sequence", "event_type", "payload", "created_at"]
        read_only_fields = fields
