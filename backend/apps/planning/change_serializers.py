from rest_framework import serializers

from apps.planning.models import ScheduleChangeBatch


class ScheduleChangeBatchSerializer(serializers.ModelSerializer[ScheduleChangeBatch]):
    class Meta:
        model = ScheduleChangeBatch
        fields = [
            "id",
            "policy",
            "operation_id",
            "status",
            "before_snapshot",
            "after_snapshot",
            "failure_reason",
            "created_at",
            "applied_at",
            "reverted_at",
        ]
