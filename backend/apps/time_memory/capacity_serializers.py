from rest_framework import serializers


class CapacityForecastSerializer(serializers.Serializer[dict[str, object]]):
    range_start = serializers.DateTimeField()
    range_end = serializers.DateTimeField()
    total_schedulable_capacity_minutes = serializers.IntegerField()
    remaining_free_minutes = serializers.IntegerField()
    available_minutes = serializers.IntegerField()
    committed_minutes = serializers.IntegerField()
    unplanned_minutes = serializers.IntegerField()
    risk = serializers.CharField()
    reason_codes = serializers.ListField(child=serializers.CharField())
