import uuid

from django.conf import settings
from django.db import models


class RiskLevel(models.TextChoices):
    HIGH = "high", "High"


class ActionProposalStatus(models.TextChoices):
    AWAITING_APPROVAL = "awaiting_approval", "Awaiting approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    EXECUTING = "executing", "Executing"
    EXECUTED = "executed", "Executed"
    FAILED = "failed", "Failed"
    EXPIRED = "expired", "Expired"


class ActionProposal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="action_proposals",
    )
    conversation = models.ForeignKey(
        "conversations.Conversation",
        on_delete=models.CASCADE,
        related_name="action_proposals",
    )
    agent_run = models.ForeignKey(
        "conversations.AgentRun",
        on_delete=models.CASCADE,
        related_name="action_proposals",
    )
    tool_call_id = models.CharField(max_length=255)
    original_request = models.TextField()
    explanation = models.TextField(blank=True)
    action_type = models.CharField(max_length=128)
    action_payload = models.JSONField(default=dict)
    original_payload = models.JSONField(default=dict)
    display_context = models.JSONField(default=dict)
    risk_level = models.CharField(
        max_length=16,
        choices=RiskLevel.choices,
        default=RiskLevel.HIGH,
    )
    status = models.CharField(
        max_length=32,
        choices=ActionProposalStatus.choices,
        default=ActionProposalStatus.AWAITING_APPROVAL,
    )
    requires_approval = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    expires_at = models.DateTimeField()
    decided_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    resumed_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(blank=True)
    decision_type = models.CharField(max_length=16, blank=True)
    decision_idempotency_key = models.UUIDField(null=True, blank=True, unique=True)
    execution_result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["agent_run", "tool_call_id"],
                name="proposal_run_tool_call_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="proposal_version_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "status", "-created_at"], name="proposal_user_status_idx"),
            models.Index(fields=["expires_at", "status"], name="proposal_expiry_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action_type}:{self.status}:{self.pk}"
