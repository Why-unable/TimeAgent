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


class EventSeriesStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    CANCELLED = "cancelled", "Cancelled"


class EventSeries(models.Model):
    """The authoritative rule and scope boundary for a finite recurring event."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    task = models.ForeignKey("tasks.Task", on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    timezone = models.CharField(max_length=64, validators=[validate_iana_timezone])
    location = models.CharField(max_length=255, blank=True)
    visibility = models.CharField(
        max_length=16,
        choices=CalendarEventVisibility.choices,
        default=CalendarEventVisibility.PRIVATE,
    )
    frequency = models.CharField(max_length=16)
    interval = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    weekdays = models.JSONField(default=list, blank=True)
    month_days = models.JSONField(default=list, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    occurrence_count = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=EventSeriesStatus.choices, default=EventSeriesStatus.ACTIVE
    )
    version = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_at__gt=models.F("start_at")),
                name="event_series_end_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="event_series_version_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.frequency})"

    def clean(self) -> None:
        super().clean()
        self.title = self.title.strip()
        self.description = self.description.strip()
        self.location = self.location.strip()
        self.frequency = self.frequency.strip().lower()
        if self.frequency not in {"daily", "weekly", "monthly"}:
            raise ValidationError({"frequency": "Frequency must be daily, weekly, or monthly"})
        if not self.title:
            raise ValidationError({"title": "Title cannot be blank"})
        if self.end_at <= self.start_at:
            raise ValidationError({"end_at": "end_at must be later than start_at"})
        if (self.ends_on is None) == (self.occurrence_count is None):
            raise ValidationError({"ends_on": "Provide exactly one finite series end condition"})
        if self.occurrence_count is not None and self.occurrence_count > 366:
            raise ValidationError(
                {"occurrence_count": "A series may contain at most 366 occurrences"}
            )
        if self.ends_on is not None and (self.ends_on - self.start_at.date()).days > 366:
            raise ValidationError({"ends_on": "A series may span at most 366 days"})
        if self.frequency != "weekly" and self.weekdays:
            raise ValidationError({"weekdays": "Only weekly series accept weekdays"})
        if self.frequency != "monthly" and self.month_days:
            raise ValidationError({"month_days": "Only monthly series accept month days"})


class CalendarEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="calendar_events",
    )
    task = models.ForeignKey(
        "tasks.Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="calendar_events",
    )
    series = models.ForeignKey(
        EventSeries,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="occurrences",
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
    external_account_reference = models.CharField(max_length=255, blank=True)
    external_calendar_id = models.CharField(max_length=255, blank=True)
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
                    models.Q(
                        source="local",
                        external_id="",
                        external_account_reference="",
                        external_calendar_id="",
                    )
                    | (
                        ~models.Q(source="local")
                        & ~models.Q(external_id="")
                        & ~models.Q(external_account_reference="")
                        & ~models.Q(external_calendar_id="")
                    )
                ),
                name="calendar_event_external_identity_consistent",
            ),
            models.UniqueConstraint(
                fields=[
                    "user",
                    "source",
                    "external_account_reference",
                    "external_calendar_id",
                    "external_id",
                ],
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
        self.external_account_reference = self.external_account_reference.strip()
        self.external_calendar_id = self.external_calendar_id.strip()
        self.recurrence_rule = self.recurrence_rule.strip()

        if not self.title:
            raise ValidationError({"title": "Title cannot be blank"})
        if not self.source:
            raise ValidationError({"source": "Source cannot be blank"})
        task = self.task
        if self.task_id is not None and (task is None or task.user_id != self.user_id):
            raise ValidationError({"task": "Linked task must belong to the same user"})

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
        external_identity = {
            "external_id": self.external_id,
            "external_account_reference": self.external_account_reference,
            "external_calendar_id": self.external_calendar_id,
        }
        if self.source == "local" and any(external_identity.values()):
            raise ValidationError(
                {
                    field_name: "Local events cannot have external identity"
                    for field_name in external_identity
                }
            )
        if self.source != "local":
            missing = [field_name for field_name, value in external_identity.items() if not value]
            if missing:
                raise ValidationError(
                    {
                        field_name: "External events require complete identity"
                        for field_name in missing
                    }
                )
