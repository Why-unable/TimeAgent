from rest_framework import serializers

from apps.planning.models import SchedulePlan


class SchedulePlanCreateSerializer(serializers.Serializer[dict[str, object]]):
    task_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    range_start = serializers.DateTimeField()
    range_end = serializers.DateTimeField()
    strategy = serializers.ChoiceField(choices=["plan_tasks_only", "create_linked_event_blocks"])
    ordering = serializers.ChoiceField(
        choices=["priority_deadline", "longest_first"],
        required=False,
        default="priority_deadline",
    )


class SchedulePlanSerializer(serializers.ModelSerializer[SchedulePlan]):
    class Meta:
        model = SchedulePlan
        fields = [
            "id",
            "strategy",
            "items",
            "constraints_snapshot",
            "decision_profile_snapshot",
            "status",
            "version",
            "created_at",
            "updated_at",
            "expires_at",
            "applied_at",
            "abandoned_at",
            "invalidated_at",
            "invalidation_reason",
        ]


class SchedulePlanApplySerializer(serializers.Serializer[dict[str, object]]):
    expected_version = serializers.IntegerField(min_value=1)


class SchedulePlanCompareSerializer(serializers.Serializer[dict[str, object]]):
    task_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    range_start = serializers.DateTimeField()
    range_end = serializers.DateTimeField()
    strategy = serializers.ChoiceField(choices=["plan_tasks_only", "create_linked_event_blocks"])


class SchedulePlanComparisonSerializer(serializers.Serializer[dict[str, object]]):
    alternatives = SchedulePlanSerializer(many=True)
    comparison = serializers.ListField(child=serializers.DictField())
    claim = serializers.CharField()


class SchedulePlanRegenerateSerializer(serializers.Serializer[dict[str, object]]):
    expected_version = serializers.IntegerField(min_value=1)
    task_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    ordering = serializers.ChoiceField(choices=["priority_deadline", "longest_first"])


class SchedulePlanItemEditSerializer(serializers.Serializer[dict[str, object]]):
    task_id = serializers.UUIDField()
    start_at = serializers.DateTimeField(required=False)
    end_at = serializers.DateTimeField(required=False)
    locked = serializers.BooleanField(required=False)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        attrs = super().validate(attrs)
        if ("start_at" in attrs) != ("end_at" in attrs):
            raise serializers.ValidationError("start_at and end_at must be provided together")
        if len(attrs) == 1:
            raise serializers.ValidationError("Provide times or locked state")
        return attrs


class SchedulePlanEditSerializer(serializers.Serializer[dict[str, object]]):
    expected_version = serializers.IntegerField(min_value=1)
    items = SchedulePlanItemEditSerializer(many=True, allow_empty=False)


class SchedulePlanValidationSerializer(serializers.Serializer[dict[str, object]]):
    expected_version = serializers.IntegerField(min_value=1)


class SchedulePlanValidationResultSerializer(serializers.Serializer[dict[str, object]]):
    plan = SchedulePlanSerializer()
    valid = serializers.BooleanField()
    reason_codes = serializers.ListField(child=serializers.CharField())
    checked_at = serializers.DateTimeField()
