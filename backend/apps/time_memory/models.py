import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class MemoryEntityType(models.TextChoices):
    EVENT = "event", "Event"
    TASK = "task", "Task"
    REMINDER = "reminder", "Reminder"


class MemoryOperation(models.TextChoices):
    CREATED = "created", "Created"
    UPDATED = "updated", "Updated"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class MemoryOperationSource(models.TextChoices):
    AGENT = "agent", "Agent"
    WEB = "web", "Web"
    ANDROID = "android", "Android"
    EXTERNAL_CALENDAR = "external_calendar", "External calendar"
    SYSTEM = "system", "System"


class TimeMemoryRefreshStatus(models.TextChoices):
    CLEAN = "clean", "Clean"
    DIRTY = "dirty", "Dirty"
    PROCESSING = "processing", "Processing"
    FAILED = "failed", "Failed"


class ScheduleChange(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="time_memory_schedule_changes",
    )
    entity_type = models.CharField(max_length=16, choices=MemoryEntityType.choices)
    entity_id = models.UUIDField()
    operation = models.CharField(max_length=16, choices=MemoryOperation.choices)
    source = models.CharField(max_length=32, choices=MemoryOperationSource.choices)
    old_snapshot = models.JSONField(default=dict, blank=True)
    new_snapshot = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["occurred_at", "id"]
        indexes = [
            models.Index(
                fields=["user", "occurred_at"],
                name="time_memory_user_time_idx",
            ),
            models.Index(
                fields=["user", "entity_type", "entity_id"],
                name="time_memory_entity_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.entity_type}:{self.entity_id}:{self.operation}"


class TimeMemoryRefreshState(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="time_memory_refresh_state",
    )
    status = models.CharField(
        max_length=16,
        choices=TimeMemoryRefreshStatus.choices,
        default=TimeMemoryRefreshStatus.DIRTY,
    )
    dirty_at = models.DateTimeField(null=True, blank=True)
    last_started_at = models.DateTimeField(null=True, blank=True)
    last_completed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    reset_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user_id}:{self.status}"


class TimeMemoryExclusionType(models.TextChoices):
    PLACE = "place", "Place"
    PATTERN = "pattern", "Pattern"


class TimeDecisionFeedbackAction(models.TextChoices):
    ACCEPT = "accept", "Accept"
    OVERRIDE = "override", "Override"
    DISABLE = "disable", "Disable"
    TOO_SHORT = "too_short", "Too short"
    TOO_LONG = "too_long", "Too long"


class TimeDecisionFeedback(models.Model):
    """User correction or consent for a derived time decision profile."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="time_decision_feedback",
    )
    category = models.CharField(max_length=64)
    action = models.CharField(max_length=16, choices=TimeDecisionFeedbackAction.choices)
    value = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=128)
    source = models.CharField(max_length=32, default="web")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "idempotency_key"],
                name="time_decision_feedback_user_key_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=["user", "category", "created_at"],
                name="time_decision_feedback_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.category}:{self.action}:{self.idempotency_key}"

    def clean(self) -> None:
        super().clean()
        if not self.category.strip():
            raise ValidationError({"category": "category cannot be blank"})
        if not self.idempotency_key.strip():
            raise ValidationError({"idempotency_key": "idempotency_key cannot be blank"})
        if not self.source.strip():
            raise ValidationError({"source": "source cannot be blank"})
        if not isinstance(self.value, dict):
            raise ValidationError({"value": "value must be an object"})


class TimeMemoryExclusion(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="time_memory_exclusions",
    )
    exclusion_type = models.CharField(max_length=16, choices=TimeMemoryExclusionType.choices)
    key = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "exclusion_type", "key"],
                name="time_memory_unique_exclusion",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.exclusion_type}:{self.key}"
