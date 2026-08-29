from typing import Any

from rest_framework import serializers


class FreeTimeRecommendationQuerySerializer(serializers.Serializer[dict[str, Any]]):
    range_start = serializers.DateTimeField()
    range_end = serializers.DateTimeField()
    duration_minutes = serializers.IntegerField(min_value=1, max_value=1440)
    max_results = serializers.IntegerField(min_value=1, max_value=50, default=8)


class FreeTimeSlotSerializer(serializers.Serializer[dict[str, Any]]):
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()
    reason_codes = serializers.ListField(child=serializers.CharField())


class FreeTimeRecommendationSerializer(serializers.Serializer[dict[str, Any]]):
    range_start = serializers.DateTimeField()
    range_end = serializers.DateTimeField()
    timezone = serializers.CharField()
    duration_minutes = serializers.IntegerField()
    slots = FreeTimeSlotSerializer(many=True)
    fallback = serializers.CharField()
