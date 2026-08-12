import uuid

from django.conf import settings
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
