import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.preferences.models import validate_iana_timezone
from common.time import NaiveDateTimeError, to_utc


class CalendarEventStatus(models.TextChoices):
    TENTATIVE = "tentative", "Tentative"
    CONFIRMED = "confirmed", "Confirmed"
    CANCELLED = "cancelled", "Cancelled"


class CalendarEventVisibility(models.TextChoices):
    PRIVATE = "private", "Private"
    PUBLIC = "public", "Public"


class CalendarEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="calendar_events",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    timezone = models.CharField(max_length=64, validators=[validate_iana_timezone])
    location = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=16,
        choices=CalendarEventStatus.choices,
        default=CalendarEventStatus.CONFIRMED,
    )
    visibility = models.CharField(
        max_length=16,
        choices=CalendarEventVisibility.choices,
        default=CalendarEventVisibility.PRIVATE,
    )
    recurrence_rule = models.TextField(blank=True)
    source = models.CharField(max_length=64, default="local")
    external_id = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_calendar_events",
    )
    version = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_at__gt=models.F("start_at")),
                name="calendar_event_end_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="calendar_event_version_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(source="local", external_id="")
                    | (~models.Q(source="local") & ~models.Q(external_id=""))
                ),
                name="calendar_event_external_identity_consistent",
            ),
            models.UniqueConstraint(
                fields=["user", "source", "external_id"],
                condition=~models.Q(external_id=""),
                name="calendar_event_unique_external_identity",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "start_at", "end_at"],
                name="calendar_event_user_time_idx",
            ),
            models.Index(
                fields=["user", "status", "start_at"],
                name="calendar_event_user_status_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title}: {self.start_at.isoformat()}–{self.end_at.isoformat()}"

    def clean(self) -> None:
        super().clean()
        self.title = self.title.strip()
        self.description = self.description.strip()
        self.location = self.location.strip()
        self.source = self.source.strip()
        self.external_id = self.external_id.strip()
        self.recurrence_rule = self.recurrence_rule.strip()

        if not self.title:
            raise ValidationError({"title": "Title cannot be blank"})
        if not self.source:
            raise ValidationError({"source": "Source cannot be blank"})

        time_errors: dict[str, str] = {}
        for field_name in ("start_at", "end_at"):
            try:
                setattr(self, field_name, to_utc(getattr(self, field_name)))
            except NaiveDateTimeError:
                time_errors[field_name] = f"{field_name} must include an explicit timezone"
        if time_errors:
            raise ValidationError(time_errors)

        if self.end_at <= self.start_at:
            raise ValidationError({"end_at": "end_at must be later than start_at"})
        if self.source == "local" and self.external_id:
            raise ValidationError({"external_id": "Local events cannot have external_id"})
        if self.source != "local" and not self.external_id:
            raise ValidationError({"external_id": "External events require external_id"})
