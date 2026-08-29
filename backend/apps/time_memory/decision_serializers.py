from typing import Any

from rest_framework import serializers

from apps.time_memory.models import TimeDecisionFeedbackAction


class DecisionProfileSerializer(serializers.Serializer[dict[str, Any]]):
    version = serializers.IntegerField()
    generated_at = serializers.DateTimeField(allow_null=True)
    category = serializers.CharField()
    enabled = serializers.BooleanField()
    default_duration_minutes = serializers.IntegerField()
    duration_multiplier = serializers.FloatField()
    confidence = serializers.FloatField()
    sample_count = serializers.IntegerField()
    source = serializers.CharField()  # type: ignore[assignment]
    evidence = serializers.ListField(child=serializers.CharField())


class DecisionFeedbackSerializer(serializers.Serializer[dict[str, Any]]):
    category = serializers.CharField(max_length=64)
    action = serializers.ChoiceField(choices=TimeDecisionFeedbackAction.values)
    value = serializers.DictField(required=False, default=dict)
    idempotency_key = serializers.CharField(max_length=128)
    source = serializers.CharField(  # type: ignore[assignment]
        max_length=32, required=False, default="web"
    )


class TaskClassificationSerializer(serializers.Serializer[dict[str, Any]]):
    category = serializers.CharField()
    confidence = serializers.FloatField()
    source = serializers.CharField()  # type: ignore[assignment]
    matched_signals = serializers.ListField(child=serializers.CharField())


class DurationRecommendationSerializer(serializers.Serializer[dict[str, Any]]):
    task_id = serializers.UUIDField()
    original_estimate_minutes = serializers.IntegerField(allow_null=True)
    recommended_minutes = serializers.IntegerField()
    duration_multiplier = serializers.FloatField()
    segment = serializers.CharField()
    confidence = serializers.FloatField()
    sample_count = serializers.IntegerField()
    source = serializers.CharField()  # type: ignore[assignment]
    fallback_reason = serializers.CharField(allow_null=True)
    evidence = serializers.ListField(child=serializers.CharField())
    classification = TaskClassificationSerializer()
    feature_version = serializers.CharField()
    expires_at = serializers.DateTimeField()
    decay_half_life_days = serializers.IntegerField()
