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


class SemanticMemoryStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUPERSEDED = "superseded", "Superseded"
    DELETED = "deleted", "Deleted"


class SemanticMemorySource(models.TextChoices):
    EXPLICIT_USER = "explicit_user", "Explicit user"
    BACKGROUND_EXTRACTION = "background_extraction", "Background extraction"
    USER_EDIT = "user_edit", "User edit"


class MemoryProposalStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    APPLIED = "applied", "Applied"
    EXPIRED = "expired", "Expired"
    CONFLICTED = "conflicted", "Conflicted"
    UNDONE = "undone", "Undone"


class MemoryProposalOperation(models.TextChoices):
    CREATE = "create", "Create"
    UPDATE = "update", "Update"
    DELETE = "delete", "Delete"
    IGNORE = "ignore", "Ignore"


class MemoryProposalSource(models.TextChoices):
    BACKGROUND_EXTRACTION = "background_extraction", "Background extraction"
    AGENT_TOOL = "agent_tool", "Agent tool"


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


class SemanticMemory(models.Model):
    """User-declared semantic memory; PostgreSQL is the authoritative record."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="semantic_memories",
    )
    category = models.CharField(max_length=64)
    key = models.CharField(max_length=128)
    value = models.JSONField(default=dict)
    status = models.CharField(
        max_length=16,
        choices=SemanticMemoryStatus.choices,
        default=SemanticMemoryStatus.ACTIVE,
    )
    source_type = models.CharField(max_length=32, choices=SemanticMemorySource.choices)
    source_run = models.ForeignKey(
        "conversations.AgentRun",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="semantic_memories",
    )
    confidence = models.FloatField(default=0.0)
    evidence_hash = models.CharField(max_length=64, blank=True)
    version = models.PositiveIntegerField(default=1)
    valid_from = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "category", "key"],
                condition=models.Q(status="active"),
                name="semantic_memory_active_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["user", "status", "category"], name="semantic_memory_lookup_idx"),
            models.Index(fields=["user", "expires_at"], name="semantic_memory_expiry_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.category}:{self.key}:{self.status}"


class MemoryProposal(models.Model):
    """Audited, policy-reviewed proposal produced by a memory extractor."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memory_proposals",
    )
    source_run = models.ForeignKey(
        "conversations.AgentRun",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="memory_proposals",
    )
    source_type = models.CharField(
        max_length=32,
        choices=MemoryProposalSource.choices,
        default=MemoryProposalSource.BACKGROUND_EXTRACTION,
    )
    target_memory = models.ForeignKey(
        SemanticMemory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="targeted_proposals",
    )
    target_version = models.PositiveIntegerField(null=True, blank=True)
    applied_memory = models.ForeignKey(
        SemanticMemory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="applied_proposals",
    )
    applied_memory_version = models.PositiveIntegerField(null=True, blank=True)
    changed_business_state = models.BooleanField(default=False)
    operation = models.CharField(max_length=16, choices=MemoryProposalOperation.choices)
    category = models.CharField(max_length=64)
    key = models.CharField(max_length=128)
    value = models.JSONField(default=dict)
    confidence = models.FloatField(default=0.0)
    evidence_hash = models.CharField(max_length=64, blank=True)
    reason_code = models.CharField(max_length=64)
    policy_reason = models.CharField(max_length=128, blank=True)
    model_alias = models.CharField(max_length=64, blank=True)
    schema_version = models.PositiveIntegerField(default=1)
    idempotency_key = models.CharField(max_length=160)
    status = models.CharField(
        max_length=16,
        choices=MemoryProposalStatus.choices,
        default=MemoryProposalStatus.PENDING,
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    undone_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "idempotency_key"],
                name="memory_proposal_user_key_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=["user", "status", "created_at"], name="memory_proposal_status_idx"
            ),
            models.Index(fields=["user", "category", "key"], name="memory_proposal_target_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.operation}:{self.category}:{self.key}:{self.status}"

    @property
    def can_undo(self) -> bool:
        return self.status == MemoryProposalStatus.APPLIED and self.changed_business_state


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
