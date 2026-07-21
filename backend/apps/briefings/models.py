import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class BriefingRunStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    PARTIAL = "partial", "Partial"
    FAILED = "failed", "Failed"


class BriefingSectionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class BriefingDefinition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="briefing_definitions",
    )
    name = models.CharField(max_length=120)
    enabled_sections = models.JSONField(default=list)
    locale = models.CharField(max_length=32, blank=True)
    timezone = models.CharField(max_length=64, blank=True)
    style = models.CharField(
        max_length=16,
        choices=[
            ("concise", "Concise"),
            ("balanced", "Balanced"),
            ("detailed", "Detailed"),
        ],
        default="balanced",
    )
    include_empty_sections = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"], name="briefing_definition_user_name_uniq"
            )
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        sections = self.enabled_sections
        if not isinstance(sections, list) or not sections:
            raise ValidationError({"enabled_sections": "At least one section is required"})
        if any(not isinstance(item, str) or not item.strip() for item in sections):
            raise ValidationError({"enabled_sections": "Section keys must be non-empty strings"})
        if len(sections) != len(set(sections)):
            raise ValidationError({"enabled_sections": "Section keys must be unique"})


class BriefingRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    definition = models.ForeignKey(
        BriefingDefinition,
        on_delete=models.PROTECT,
        related_name="runs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="briefing_runs",
    )
    conversation = models.ForeignKey(
        "conversations.Conversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="briefing_runs",
    )
    agent_run = models.OneToOneField(
        "conversations.AgentRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="briefing_run",
    )
    operation_id = models.UUIDField(unique=True)
    trigger_type = models.CharField(max_length=32)
    target_date = models.DateField()
    timezone = models.CharField(max_length=64)
    status = models.CharField(
        max_length=16,
        choices=BriefingRunStatus.choices,
        default=BriefingRunStatus.PENDING,
    )
    definition_snapshot = models.JSONField(default=dict)
    structured_result = models.JSONField(default=dict)
    research_report = models.JSONField(default=dict)
    rendered_markdown = models.TextField(blank=True)
    warnings = models.JSONField(default=list)
    model_config_snapshot = models.JSONField(default=dict)
    prompt_version = models.CharField(max_length=64, blank=True)
    failure_code = models.CharField(max_length=64, blank=True)
    failure_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="brief_run_user_created_idx"),
            models.Index(fields=["status", "created_at"], name="brief_run_status_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.target_date}: {self.status}"


class BriefingSectionRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    briefing_run = models.ForeignKey(
        BriefingRun,
        on_delete=models.CASCADE,
        related_name="section_runs",
    )
    section_key = models.CharField(max_length=64)
    status = models.CharField(
        max_length=16,
        choices=BriefingSectionStatus.choices,
        default=BriefingSectionStatus.PENDING,
    )
    source_snapshot = models.JSONField(default=dict)
    source_references = models.JSONField(default=list)
    warning = models.TextField(blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["section_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["briefing_run", "section_key"],
                name="briefing_section_run_key_uniq",
            )
        ]

    def __str__(self) -> str:
        return f"{self.briefing_run_id}:{self.section_key}:{self.status}"
