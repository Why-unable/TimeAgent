import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


def default_schedule_plan_expiry() -> datetime:
    return timezone.now() + timedelta(seconds=settings.SCHEDULE_PLAN_TTL_SECONDS)


class SchedulePlanStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    APPLIED = "applied", "Applied"
    SUPERSEDED = "superseded", "Superseded"
    ABANDONED = "abandoned", "Abandoned"
    INVALIDATED = "invalidated", "Invalidated"


class SchedulePlan(models.Model):
    """A reviewable, immutable-at-apply planning proposal; not a calendar fact."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    strategy = models.CharField(max_length=32)
    items = models.JSONField(default=list)
    constraints_snapshot = models.JSONField(default=dict)
    decision_profile_snapshot = models.JSONField(default=dict)
    status = models.CharField(
        max_length=16,
        choices=SchedulePlanStatus.choices,
        default=SchedulePlanStatus.DRAFT,
    )
    version = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(default=default_schedule_plan_expiry)
    applied_at = models.DateTimeField(null=True, blank=True)
    abandoned_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    invalidation_reason = models.CharField(max_length=64, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["user", "status", "created_at"],
                name="plan_user_status_created_idx",
            )
        ]

    def __str__(self) -> str:
        return f"Schedule plan {self.pk} ({self.status})"


class AutomationPolicy(models.Model):
    """Explicit user consent boundary for future schedule automation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="automation_policies"
    )
    name = models.CharField(max_length=120)
    enabled = models.BooleanField(default=False)
    allow_task_reschedule = models.BooleanField(default=False)
    max_moves_per_run = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1)]
    )
    requires_approval = models.BooleanField(default=True)
    authorized_task_ids = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"], name="automation_policy_user_name_uniq"
            )
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": "Policy name cannot be blank"})
        if self.max_moves_per_run > 20:
            raise ValidationError({"max_moves_per_run": "Must be at most 20"})
        if self.enabled and not self.allow_task_reschedule:
            raise ValidationError(
                {"allow_task_reschedule": "Enabled automation must explicitly allow rescheduling"}
            )
        if not isinstance(self.authorized_task_ids, list) or any(
            not isinstance(task_id, str) or not task_id.strip()
            for task_id in self.authorized_task_ids
        ):
            raise ValidationError(
                {"authorized_task_ids": "Must be a list of non-empty task UUID strings"}
            )
        if len(set(self.authorized_task_ids)) != len(self.authorized_task_ids):
            raise ValidationError({"authorized_task_ids": "Task IDs must be unique"})


class ScheduleChangeBatchStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPLIED = "applied", "Applied"
    REVERTED = "reverted", "Reverted"
    FAILED = "failed", "Failed"


class ScheduleChangeBatch(models.Model):
    """Auditable before/after snapshot for a bounded schedule mutation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    policy = models.ForeignKey(AutomationPolicy, on_delete=models.PROTECT)
    operation_id = models.UUIDField(unique=True)
    status = models.CharField(
        max_length=16,
        choices=ScheduleChangeBatchStatus.choices,
        default=ScheduleChangeBatchStatus.PENDING,
    )
    before_snapshot = models.JSONField(default=list)
    after_snapshot = models.JSONField(default=list)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    reverted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["user", "status", "created_at"], name="planning_sc_user_id_7e1b9c_idx"
            )
        ]

    def __str__(self) -> str:
        return f"Schedule change batch {self.pk} ({self.status})"
