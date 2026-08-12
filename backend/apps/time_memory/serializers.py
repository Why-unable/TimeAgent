from rest_framework import serializers


class TimeMemoryStatusSerializer(serializers.Serializer[dict[str, object]]):
    profile = serializers.JSONField(allow_null=True)
    refresh_status = serializers.CharField()
    dirty_at = serializers.DateTimeField(allow_null=True)
    last_completed_at = serializers.DateTimeField(allow_null=True)
    last_error = serializers.CharField()
