from rest_framework import serializers

from apps.planning.models import AutomationPolicy


class AutomationPolicySerializer(serializers.ModelSerializer[AutomationPolicy]):
    authorized_task_ids = serializers.ListField(
        child=serializers.UUIDField(), read_only=True
    )

    class Meta:
        model = AutomationPolicy
        fields = [
            "id",
            "name",
            "enabled",
            "allow_task_reschedule",
            "max_moves_per_run",
            "requires_approval",
            "authorized_task_ids",
            "created_at",
            "updated_at",
        ]


class AutomationPolicyWriteSerializer(serializers.ModelSerializer[AutomationPolicy]):
    authorized_task_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )

    class Meta:
        model = AutomationPolicy
        fields = [
            "name",
            "enabled",
            "allow_task_reschedule",
            "max_moves_per_run",
            "requires_approval",
            "authorized_task_ids",
        ]
