import uuid

from django.conf import settings
from django.db import models


class AgentRunStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    WAITING_APPROVAL = "waiting_approval", "Waiting for approval"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class ToolCallStatus(models.TextChoices):
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent_conversations",
    )
    title = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-created_at"]
        indexes = [models.Index(fields=["user", "-updated_at"], name="conv_user_updated_idx")]

    def __str__(self) -> str:
        return self.title or str(self.pk)


class AgentRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="runs",
    )
    operation_id = models.UUIDField(unique=True)
    request_id = models.CharField(max_length=128)
    execution_task_id = models.CharField(max_length=255, blank=True, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=AgentRunStatus.choices,
        default=AgentRunStatus.PENDING,
    )
    input_message = models.TextField()
    final_response = models.TextField(blank=True)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["conversation", "created_at"], name="run_conv_created_idx"),
            models.Index(fields=["status", "created_at"], name="run_status_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.pk}: {self.status}"


class AgentEvent(models.Model):
    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="events")
    sequence = models.PositiveIntegerField()
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "sequence"], name="agent_event_run_sequence_uniq"
            )
        ]

    def __str__(self) -> str:
        return f"{self.run_id}:{self.sequence}:{self.event_type}"


class ToolCallAudit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="tool_calls")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tool_call_id = models.CharField(max_length=255)
    tool_name = models.CharField(max_length=128)
    risk_level = models.CharField(max_length=16, default="read")
    arguments = models.JSONField(default=dict)
    result = models.JSONField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=ToolCallStatus.choices,
        default=ToolCallStatus.RUNNING,
    )
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["started_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "tool_call_id"],
                name="tool_audit_run_call_uniq",
            )
        ]

    def __str__(self) -> str:
        return f"{self.tool_name}:{self.tool_call_id}"
