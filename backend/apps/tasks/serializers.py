from typing import Any

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from apps.tasks.models import Task, TaskPriority, TaskStatus
from apps.tasks.services import CreateTaskCommand, TaskService, UpdateTaskCommand
from common.serializers import ExplicitTimezoneDateTimeField, StrictSerializer


class TaskSerializer(serializers.ModelSerializer[Task]):
    class Meta:
        model = Task
        fields = [
            "id",
            "project",
            "parent_task",
            "title",
            "description",
            "status",
            "priority",
            "due_at",
            "estimated_minutes",
            "planned_start_at",
            "planned_end_at",
            "actual_started_at",
            "completed_at",
            "source",
            "tags",
            "created_at",
            "updated_at",
        ]


class TaskFieldsSerializer(StrictSerializer):
    project = serializers.CharField(required=False, allow_blank=True, max_length=255)
    parent_task = serializers.PrimaryKeyRelatedField(
        required=False,
        allow_null=True,
        queryset=Task.objects.none(),
    )
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    priority = serializers.ChoiceField(
        required=False,
        choices=TaskPriority.choices,
    )
    due_at = ExplicitTimezoneDateTimeField(required=False, allow_null=True)
    estimated_minutes = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
    )
    planned_start_at = ExplicitTimezoneDateTimeField(
        required=False,
        allow_null=True,
    )
    planned_end_at = ExplicitTimezoneDateTimeField(
        required=False,
        allow_null=True,
    )
    source = serializers.CharField(  # type: ignore[assignment]
        required=False,
        max_length=64,
    )
    tags = serializers.ListField(
        required=False,
        child=serializers.CharField(),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        parent_field = self.fields["parent_task"]
        if isinstance(user, User) and isinstance(
            parent_field,
            serializers.PrimaryKeyRelatedField,
        ):
            parent_field.queryset = Task.objects.filter(user=user)


class CreateTaskSerializer(TaskFieldsSerializer):
    def create(self, validated_data: dict[str, Any]) -> Task:
        user = self.context["request"].user
        if not isinstance(user, User):
            raise serializers.ValidationError("A persisted user is required")
        try:
            return TaskService.create_task(CreateTaskCommand(user=user, **validated_data))
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc


class UpdateTaskSerializer(TaskFieldsSerializer):
    title = serializers.CharField(required=False, max_length=255)
    project = serializers.CharField(required=False, allow_blank=True, max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    priority = serializers.ChoiceField(required=False, choices=TaskPriority.choices)
    due_at = ExplicitTimezoneDateTimeField(required=False, allow_null=True)
    estimated_minutes = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    planned_start_at = ExplicitTimezoneDateTimeField(required=False, allow_null=True)
    planned_end_at = ExplicitTimezoneDateTimeField(required=False, allow_null=True)
    source = serializers.CharField(required=False, max_length=64)
    tags = serializers.ListField(required=False, child=serializers.CharField())

    @transaction.atomic
    def update(self, instance: Task, validated_data: dict[str, Any]) -> Task:
        user = self.context["request"].user
        if not isinstance(user, User):
            raise serializers.ValidationError("A persisted user is required")

        has_planned_start = "planned_start_at" in validated_data
        has_planned_end = "planned_end_at" in validated_data
        planned_start_at = validated_data.pop("planned_start_at", instance.planned_start_at)
        planned_end_at = validated_data.pop("planned_end_at", instance.planned_end_at)
        try:
            task = instance
            if validated_data:
                task = TaskService.update_task(
                    UpdateTaskCommand(
                        user=user,
                        task_id=instance.id,
                        changes=validated_data,
                    )
                )
            if has_planned_start or has_planned_end:
                task = TaskService.reschedule_task(
                    task_id=instance.id,
                    user=user,
                    planned_start_at=planned_start_at,
                    planned_end_at=planned_end_at,
                )
            return task
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        if not attrs:
            raise serializers.ValidationError("At least one task field is required")
        return attrs


class TaskListQuerySerializer(StrictSerializer):
    status = serializers.MultipleChoiceField(required=False, choices=TaskStatus.choices)
    due_before = ExplicitTimezoneDateTimeField(required=False)
    planned_starts_before = ExplicitTimezoneDateTimeField(required=False)
    planned_ends_after = ExplicitTimezoneDateTimeField(required=False)
