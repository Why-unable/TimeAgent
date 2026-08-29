from rest_framework import serializers


class LocalReplanPreviewRequestSerializer(serializers.Serializer[dict[str, object]]):
    blocked_start = serializers.DateTimeField()
    blocked_end = serializers.DateTimeField()
    movable_task_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    horizon_end = serializers.DateTimeField()


class LocalReplanApplyRequestSerializer(LocalReplanPreviewRequestSerializer):
    policy_id = serializers.UUIDField()
    operation_id = serializers.UUIDField()


class LocalReplanPreviewSerializer(serializers.Serializer[dict[str, object]]):
    blocked_start = serializers.DateTimeField()
    blocked_end = serializers.DateTimeField()
    moved_items = serializers.ListField()
    unchanged_task_ids = serializers.ListField()
    stability_cost = serializers.DictField(child=serializers.IntegerField(min_value=0))
    reason = serializers.CharField()


class DisruptionDetectionRequestSerializer(serializers.Serializer[dict[str, object]]):
    range_start = serializers.DateTimeField()
    range_end = serializers.DateTimeField()


class ScheduleDisruptionSerializer(serializers.Serializer[dict[str, object]]):
    task_id = serializers.UUIDField()
    task_title = serializers.CharField()
    task_version = serializers.IntegerField(min_value=1)
    event_id = serializers.UUIDField()
    event_title = serializers.CharField()
    blocked_start = serializers.DateTimeField()
    blocked_end = serializers.DateTimeField()
    overlap_minutes = serializers.IntegerField(min_value=1)
    reason_codes = serializers.ListField(child=serializers.CharField())
