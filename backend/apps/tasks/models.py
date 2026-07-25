import uuid
from datetime import datetime
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from common.time import NaiveDateTimeError, to_utc


class TaskStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    IN_PROGRESS = "in_progress", "In progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class TaskPriority(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    URGENT = "urgent", "Urgent"


class InvalidTaskTransitionError(ValueError):
    pass


class Task(models.Model):
    TRANSITIONS = {
        TaskStatus.PENDING: frozenset(
            {
                TaskStatus.IN_PROGRESS,
                TaskStatus.COMPLETED,
                TaskStatus.CANCELLED,
            }
        ),
        TaskStatus.IN_PROGRESS: frozenset(
            {
                TaskStatus.PENDING,
                TaskStatus.COMPLETED,
                TaskStatus.CANCELLED,
            }
        ),
        TaskStatus.COMPLETED: frozenset(),
        TaskStatus.CANCELLED: frozenset(),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    project = models.CharField(max_length=255, blank=True)
    parent_task = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subtasks",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=TaskStatus.choices,
        default=TaskStatus.PENDING,
    )
    priority = models.CharField(
        max_length=16,
        choices=TaskPriority.choices,
        default=TaskPriority.MEDIUM,
    )
    due_at = models.DateTimeField(null=True, blank=True)
    estimated_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    planned_start_at = models.DateTimeField(null=True, blank=True)
    planned_end_at = models.DateTimeField(null=True, blank=True)
    actual_started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=64, default="local")
    tags = models.JSONField(default=list, blank=True)
    version = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "due_at", "created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(planned_start_at__isnull=True, planned_end_at__isnull=True)
                    | (
                        models.Q(planned_start_at__isnull=False)
                        & models.Q(planned_end_at__isnull=False)
                        & models.Q(planned_end_at__gt=models.F("planned_start_at"))
                    )
                ),
                name="task_planned_range_consistent",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(estimated_minutes__isnull=True) | models.Q(estimated_minutes__gte=1)
                ),
                name="task_estimated_minutes_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status=TaskStatus.COMPLETED, completed_at__isnull=False)
                    | (~models.Q(status=TaskStatus.COMPLETED) & models.Q(completed_at__isnull=True))
                ),
                name="task_completed_timestamp_consistent",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=TaskStatus.IN_PROGRESS)
                    | models.Q(actual_started_at__isnull=False)
                ),
                name="task_in_progress_has_start",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="task_version_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "status", "due_at"],
                name="task_user_status_due_idx",
            ),
            models.Index(
                fields=["user", "planned_start_at"],
                name="task_user_planned_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    def clean(self) -> None:
        super().clean()
        self.title = self.title.strip()
        self.description = self.description.strip()
        self.project = self.project.strip()
        self.source = self.source.strip()

        if not self.title:
            raise ValidationError({"title": "Title cannot be blank"})
        if not self.source:
            raise ValidationError({"source": "Source cannot be blank"})

        self._normalize_times()
        self._validate_planned_range()
        self._validate_status_timestamps()
        self._validate_parent()
        self.tags = self._normalize_tags(self.tags)

    def _normalize_times(self) -> None:
        errors: dict[str, str] = {}
        for field_name in (
            "due_at",
            "planned_start_at",
            "planned_end_at",
            "actual_started_at",
            "completed_at",
        ):
            value = getattr(self, field_name)
            if value is None:
                continue
            try:
                setattr(self, field_name, to_utc(value))
            except NaiveDateTimeError:
                errors[field_name] = f"{field_name} must include an explicit timezone"
        if errors:
            raise ValidationError(errors)

    def _validate_planned_range(self) -> None:
        planned_start = self.planned_start_at
        planned_end = self.planned_end_at
        if (planned_start is None) != (planned_end is None):
            raise ValidationError(
                {"planned_end_at": "Planned start and end must be provided together"}
            )
        if planned_start is not None and planned_end is not None and planned_end <= planned_start:
            raise ValidationError(
                {"planned_end_at": "planned_end_at must be later than planned_start_at"}
            )

    def _validate_status_timestamps(self) -> None:
        if self.status == TaskStatus.COMPLETED and self.completed_at is None:
            raise ValidationError({"completed_at": "Completed tasks require completed_at"})
        if self.status != TaskStatus.COMPLETED and self.completed_at is not None:
            raise ValidationError({"completed_at": "Only completed tasks can have completed_at"})
        if self.status == TaskStatus.IN_PROGRESS and self.actual_started_at is None:
            raise ValidationError(
                {"actual_started_at": "In-progress tasks require actual_started_at"}
            )

    def _validate_parent(self) -> None:
        parent = self.parent_task
        if parent is None:
            return
        if parent.user_id != self.user_id:
            raise ValidationError({"parent_task": "Parent task must belong to the same user"})

        visited = {self.pk}
        ancestor: Task | None = parent
        while ancestor is not None:
            if ancestor.pk in visited:
                raise ValidationError({"parent_task": "Task hierarchy cannot contain cycles"})
            visited.add(ancestor.pk)
            ancestor = ancestor.parent_task

    @staticmethod
    def _normalize_tags(value: Any) -> list[str]:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValidationError({"tags": "Tags must be a list of strings"})
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValidationError({"tags": "Tags cannot contain blank values"})
        if len(set(normalized)) != len(normalized):
            raise ValidationError({"tags": "Tags must be unique"})
        return normalized

    def can_transition_to(self, new_status: TaskStatus | str) -> bool:
        try:
            normalized_status = TaskStatus(new_status)
            current_status = TaskStatus(self.status)
        except ValueError:
            return False
        return normalized_status in self.TRANSITIONS[current_status]

    def transition_to(
        self,
        new_status: TaskStatus | str,
        *,
        occurred_at: datetime,
    ) -> None:
        try:
            normalized_status = TaskStatus(new_status)
            occurred_at_utc = to_utc(occurred_at)
        except NaiveDateTimeError as exc:
            raise InvalidTaskTransitionError(
                "occurred_at must include an explicit timezone"
            ) from exc
        except ValueError as exc:
            raise InvalidTaskTransitionError(str(exc)) from exc

        if not self.can_transition_to(normalized_status):
            raise InvalidTaskTransitionError(
                f"Cannot transition task from {self.status} to {normalized_status}"
            )

        if normalized_status == TaskStatus.IN_PROGRESS:
            self.actual_started_at = self.actual_started_at or occurred_at_utc
        elif normalized_status == TaskStatus.COMPLETED:
            self.completed_at = occurred_at_utc

        self.status = normalized_status
