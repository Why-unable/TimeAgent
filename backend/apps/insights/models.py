import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class TemporalInsightStatus(models.TextChoices):
    OPEN = "open", "Open"
    SNOOZED = "snoozed", "Snoozed"
    DISMISSED = "dismissed", "Dismissed"
    ACTIONED = "actioned", "Actioned"
    EXPIRED = "expired", "Expired"
    FALSE_POSITIVE = "false_positive", "False positive"


class TemporalInsight(models.Model):
    """A deterministic, evidence-backed candidate for the insight inbox."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="temporal_insights"
    )
    kind = models.CharField(max_length=64)
    severity = models.CharField(max_length=16)
    status = models.CharField(
        max_length=16, choices=TemporalInsightStatus.choices, default=TemporalInsightStatus.OPEN
    )
    title = models.CharField(max_length=255)
    summary = models.TextField()
    evidence = models.JSONField(default=dict, blank=True)
    deduplication_key = models.CharField(max_length=255)
    detected_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    snoozed_until = models.DateTimeField(null=True, blank=True)
    acted_at = models.DateTimeField(null=True, blank=True)
    attention_decision = models.CharField(max_length=32, default="STORE")
    attention_reason = models.CharField(max_length=128, blank=True)
    attention_decided_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-detected_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "deduplication_key"], name="insight_user_dedup_uniq"
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "status", "expires_at"], name="insight_user_status_expiry_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.kind}:{self.status}"

    def clean(self) -> None:
        super().clean()
        if not self.kind.strip() or not self.title.strip() or not self.summary.strip():
            raise ValidationError("Insight kind, title and summary are required")
        if self.expires_at <= self.detected_at:
            raise ValidationError({"expires_at": "expires_at must be later than detected_at"})
        if not isinstance(self.evidence, dict):
            raise ValidationError({"evidence": "evidence must be an object"})
