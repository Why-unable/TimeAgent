import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def default_interaction_expiry() -> datetime:
    return timezone.now() + timedelta(days=14)


class InteractionType(models.TextChoices):
    PRIORITY_RANKING = "priority_ranking", "Priority ranking"
    PLAN_TIMELINE_EDIT = "plan_timeline_edit", "Plan timeline edit"
    TASK_COMPLETION = "task_completion", "Task completion feedback"
    MEMORY_SUGGESTION = "memory_suggestion", "Memory suggestion"


class InteractionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"
    ABANDONED = "abandoned", "Abandoned"
    EXPIRED = "expired", "Expired"
    STALE = "stale", "Stale"


class InteractionArtifact(models.Model):
    """Durable, typed user decision surface; payloads contain data, never UI markup."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    conversation = models.ForeignKey(
        "conversations.Conversation", null=True, blank=True, on_delete=models.CASCADE
    )
    agent_run = models.ForeignKey(
        "conversations.AgentRun", null=True, blank=True, on_delete=models.CASCADE
    )
    plan = models.ForeignKey(
        "planning.SchedulePlan", null=True, blank=True, on_delete=models.CASCADE
    )
    plan_version = models.PositiveIntegerField(null=True, blank=True)
    task = models.ForeignKey("tasks.Task", null=True, blank=True, on_delete=models.CASCADE)
    type = models.CharField(max_length=32, choices=InteractionType.choices)
    payload = models.JSONField(default=dict)
    allowed_actions = models.JSONField(default=list)
    status = models.CharField(
        max_length=16, choices=InteractionStatus.choices, default=InteractionStatus.PENDING
    )
    expires_at = models.DateTimeField(default=default_interaction_expiry)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "status", "expires_at"], name="inter_user_status_exp_idx"),
            models.Index(fields=["plan", "status"], name="interaction_plan_status_idx"),
            models.Index(fields=["task", "status"], name="interaction_task_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        type__in=[
                            InteractionType.PRIORITY_RANKING,
                            InteractionType.PLAN_TIMELINE_EDIT,
                        ],
                        plan__isnull=False,
                    )
                    | models.Q(
                        type__in=[
                            InteractionType.TASK_COMPLETION,
                            InteractionType.MEMORY_SUGGESTION,
                        ],
                        task__isnull=False,
                    )
                ),
                name="inter_target_type_ck",
            ),
            models.UniqueConstraint(
                fields=["user", "type", "plan"],
                condition=models.Q(plan__isnull=False, status=InteractionStatus.PENDING),
                name="inter_user_type_plan_pending",
            ),
            models.UniqueConstraint(
                fields=["user", "type", "task"],
                condition=models.Q(task__isnull=False, status=InteractionStatus.PENDING),
                name="inter_user_type_task_pending",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.type}:{self.pk}:{self.status}"

    def clean(self) -> None:
        super().clean()
        if not isinstance(self.payload, dict):
            raise ValidationError({"payload": "payload must be an object"})
        if not isinstance(self.allowed_actions, list) or any(
            not isinstance(action, str) for action in self.allowed_actions
        ):
            raise ValidationError({"allowed_actions": "allowed_actions must be a string list"})
        if self.plan_id:
            plan = self.plan
            if plan is None or plan.user_id != self.user_id:
                raise ValidationError({"plan": "Plan must belong to the interaction user"})
        if self.task_id:
            task = self.task
            if task is None or task.user_id != self.user_id:
                raise ValidationError({"task": "Task must belong to the interaction user"})
        if self.conversation_id:
            conversation = self.conversation
            if conversation is None or conversation.user_id != self.user_id:
                raise ValidationError(
                    {"conversation": "Conversation must belong to the interaction user"}
                )
        if self.agent_run_id:
            agent_run = self.agent_run
            if (
                agent_run is None
                or agent_run.conversation_id is None
                or agent_run.conversation.user_id != self.user_id
            ):
                raise ValidationError(
                    {"agent_run": "Agent run must belong to the interaction user"}
                )


class InteractionSubmission(models.Model):
    """Idempotent decision history for an interaction artifact."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    interaction = models.ForeignKey(
        InteractionArtifact, on_delete=models.CASCADE, related_name="submissions"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    expected_version = models.PositiveIntegerField()
    action = models.CharField(max_length=32)
    values = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    idempotency_key = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "idempotency_key"], name="inter_user_idem_uniq")
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.interaction_id}:{self.action}:{self.idempotency_key}"

    def clean(self) -> None:
        super().clean()
        self.idempotency_key = self.idempotency_key.strip()
        if not self.idempotency_key:
            raise ValidationError({"idempotency_key": "idempotency_key cannot be blank"})
        if self.interaction_id and self.interaction.user_id != self.user_id:
            raise ValidationError({"interaction": "Interaction must belong to the submission user"})
        for field in ("values", "result"):
            if not isinstance(getattr(self, field), dict):
                raise ValidationError({field: f"{field} must be an object"})


class InteractionTelemetryEventType(models.TextChoices):
    SHOWN = "interaction_shown", "Interaction shown"
    STARTED = "interaction_started", "Interaction started"
    COMPLETED = "interaction_completed", "Interaction completed"
    ABANDONED = "interaction_abandoned", "Interaction abandoned"
    COMPLETION_FEEDBACK_RATE = "completion_feedback_rate", "Completion feedback rate"
    PLAN_ACCEPTED = "plan_acceptance_after_interaction", "Plan accepted after interaction"
    MEMORY_SHOWN = "memory_suggestion_shown", "Memory suggestion shown"
    MEMORY_ACCEPTED = "memory_suggestion_accepted", "Memory suggestion accepted"
    DAY_CLOSE_COMPLETED = "day_close_completion_rate", "Day close completed"
    INVALID_DROP = "invalid_drop", "Invalid drop"
    PLAN_EDIT = "plan_edit", "Plan edit"
    UNDO = "undo", "Undo"


class InteractionTelemetryEvent(models.Model):
    """Allowlisted anonymous event metrics; deliberately has no user or content FK."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=48, choices=InteractionTelemetryEventType.choices)
    interaction_type = models.CharField(max_length=32, choices=InteractionType.choices)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    drag_count = models.PositiveSmallIntegerField(default=0)
    invalid_drop_count = models.PositiveSmallIntegerField(default=0)
    undo_count = models.PositiveSmallIntegerField(default=0)
    plan_edit_count = models.PositiveSmallIntegerField(default=0)
    actual_vs_planned_ratio = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event_type", "created_at"], name="interaction_event_time_idx")
        ]

    def __str__(self) -> str:
        return f"{self.event_type}:{self.interaction_type}:{self.pk}"
