from rest_framework import serializers

from apps.time_memory.models import MemoryProposal, SemanticMemory


class TimeMemoryStatusSerializer(serializers.Serializer[dict[str, object]]):
    profile = serializers.JSONField(allow_null=True)
    refresh_status = serializers.CharField()
    dirty_at = serializers.DateTimeField(allow_null=True)
    last_completed_at = serializers.DateTimeField(allow_null=True)
    last_error = serializers.CharField()


class SemanticMemorySerializer(serializers.Serializer[SemanticMemory]):
    id = serializers.UUIDField()
    category = serializers.CharField()
    key = serializers.CharField()
    value = serializers.DictField()
    status = serializers.CharField()
    source_type = serializers.CharField()
    confidence = serializers.FloatField()
    version = serializers.IntegerField()
    valid_from = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class MemoryProposalSerializer(serializers.Serializer[MemoryProposal]):
    id = serializers.UUIDField()
    operation = serializers.CharField()
    category = serializers.CharField()
    key = serializers.CharField()
    value = serializers.DictField()
    confidence = serializers.FloatField()
    reason_code = serializers.CharField()
    policy_reason = serializers.CharField()
    status = serializers.CharField()
    source_run_id = serializers.UUIDField(allow_null=True)
    source_type = serializers.CharField()
    target_memory_id = serializers.UUIDField(allow_null=True)
    target_version = serializers.IntegerField(allow_null=True)
    applied_memory_id = serializers.UUIDField(allow_null=True)
    applied_memory_version = serializers.IntegerField(allow_null=True)
    changed_business_state = serializers.BooleanField()
    can_undo = serializers.BooleanField()
    undone_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class MemoryProposalDecisionSerializer(serializers.Serializer[dict[str, object]]):
    approve = serializers.BooleanField()
