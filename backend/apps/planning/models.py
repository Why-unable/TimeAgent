import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class SchedulePlanStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    APPLIED = "applied", "Applied"
    SUPERSEDED = "superseded", "Superseded"


class SchedulePlan(models.Model):
    """A reviewable, immutable-at-apply planning proposal; not a calendar fact."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    strategy = models.CharField(max_length=32)
    items = models.JSONField(default=list)
    status = models.CharField(
        max_length=16,
        choices=SchedulePlanStatus.choices,
        default=SchedulePlanStatus.DRAFT,
    )
    version = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["user", "status", "created_at"],
                name="plan_user_status_created_idx",
            )
        ]

    def __str__(self) -> str:
        return f"Schedule plan {self.pk} ({self.status})"
