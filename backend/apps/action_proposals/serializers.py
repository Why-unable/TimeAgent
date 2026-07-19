from typing import Any

from rest_framework import serializers

from apps.action_proposals.models import ActionProposal


class ActionProposalSerializer(serializers.ModelSerializer[ActionProposal]):
    conversation_id = serializers.UUIDField(read_only=True)
    agent_run_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ActionProposal
        fields = [
            "id",
            "conversation_id",
            "agent_run_id",
            "original_request",
            "explanation",
            "action_type",
            "action_payload",
            "original_payload",
            "display_context",
            "risk_level",
            "status",
            "requires_approval",
            "version",
            "expires_at",
            "decided_at",
            "approved_at",
            "resumed_at",
            "executed_at",
            "decision_reason",
            "execution_result",
            "error",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ProposalDecisionSerializer(serializers.Serializer[Any]):
    expected_version = serializers.IntegerField(min_value=1)
    operation_id = serializers.UUIDField()
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


class ProposalEditDecisionSerializer(ProposalDecisionSerializer):
    action_payload = serializers.JSONField()

    def validate_action_payload(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or not value:
            raise serializers.ValidationError("action_payload must be a non-empty object")
        return value


class ProposalDecisionResponseSerializer(serializers.Serializer[Any]):
    proposal = ActionProposalSerializer(read_only=True)
    resume_queued = serializers.BooleanField(read_only=True)
