import uuid
from datetime import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.preferences.models import validate_iana_timezone
from common.time import NaiveDateTimeError, to_utc


class ReminderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    QUEUED = "queued", "Queued"
    SENDING = "sending", "Sending"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    MISSED = "missed", "Missed"


class ReminderTargetType(models.TextChoices):
    CUSTOM = "custom", "Custom"
    CALENDAR_EVENT = "calendar_event", "Calendar event"
    TASK = "task", "Task"


class ReminderChannel(models.TextChoices):
    CONSOLE = "console", "Console"
    EMAIL = "email", "Email"
    TELEGRAM = "telegram", "Telegram"
    BROWSER = "browser", "Browser"


class ReminderScheduleAnchor(models.TextChoices):
    TASK_PLANNED_START = "task_planned_start", "Task planned start"
    EVENT_START = "event_start", "Event start"


class InvalidReminderTransitionError(ValueError):
    pass


class Reminder(models.Model):
    TRANSITIONS = {
        ReminderStatus.PENDING: frozenset(
            {
                ReminderStatus.QUEUED,
                ReminderStatus.CANCELLED,
                ReminderStatus.MISSED,
            }
        ),
        ReminderStatus.QUEUED: frozenset(
            {
                ReminderStatus.SENDING,
                ReminderStatus.FAILED,
                ReminderStatus.CANCELLED,
                ReminderStatus.MISSED,
            }
        ),
        ReminderStatus.SENDING: frozenset(
            {
                ReminderStatus.SENT,
                ReminderStatus.FAILED,
            }
        ),
        ReminderStatus.FAILED: frozenset(
            {
                ReminderStatus.QUEUED,
                ReminderStatus.CANCELLED,
                ReminderStatus.MISSED,
            }
        ),
        ReminderStatus.SENT: frozenset(),
        ReminderStatus.CANCELLED: frozenset(),
        ReminderStatus.MISSED: frozenset(),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reminders",
    )
    target_type = models.CharField(
        max_length=32,
        choices=ReminderTargetType.choices,
        default=ReminderTargetType.CUSTOM,
    )
    target_id = models.UUIDField(null=True, blank=True)
    schedule_anchor = models.CharField(
        max_length=32,
        choices=ReminderScheduleAnchor.choices,
        blank=True,
    )
    offset_minutes = models.PositiveIntegerField(null=True, blank=True)
    title = models.CharField(max_length=255)
    trigger_at = models.DateTimeField()
    timezone = models.CharField(
        max_length=64,
        validators=[validate_iana_timezone],
    )
    channel = models.CharField(
        max_length=32,
        choices=ReminderChannel.choices,
        default=ReminderChannel.CONSOLE,
    )
    status = models.CharField(
        max_length=16,
        choices=ReminderStatus.choices,
        default=ReminderStatus.PENDING,
    )
    deduplication_key = models.CharField(max_length=128)
    queued_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    failure_reason = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["trigger_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "deduplication_key"],
                name="reminder_unique_user_deduplication_key",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(target_type=ReminderTargetType.CUSTOM, target_id__isnull=True)
                    | (
                        ~models.Q(target_type=ReminderTargetType.CUSTOM)
                        & models.Q(target_id__isnull=False)
                    )
                ),
                name="reminder_target_reference_consistent",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(schedule_anchor="", offset_minutes__isnull=True)
                    | (
                        ~models.Q(schedule_anchor="")
                        & models.Q(offset_minutes__isnull=False, offset_minutes__gte=0)
                    )
                ),
                name="reminder_schedule_metadata_consistent",
            ),
            models.CheckConstraint(
                condition=(~models.Q(status=ReminderStatus.SENT) | models.Q(sent_at__isnull=False)),
                name="reminder_sent_has_timestamp",
            ),
            models.CheckConstraint(
                condition=(~models.Q(status=ReminderStatus.FAILED) | ~models.Q(failure_reason="")),
                name="reminder_failed_has_reason",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="reminder_version_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "trigger_at"],
                name="reminder_due_scan_idx",
            ),
            models.Index(
                fields=["user", "status"],
                name="reminder_user_status_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} at {self.trigger_at.isoformat()}"

    def clean(self) -> None:
        super().clean()
        self.title = self.title.strip()
        self.deduplication_key = self.deduplication_key.strip()

        if not self.title:
            raise ValidationError({"title": "Title cannot be blank"})
        if not self.deduplication_key:
            raise ValidationError({"deduplication_key": "Deduplication key cannot be blank"})
        try:
            self.trigger_at = to_utc(self.trigger_at)
        except NaiveDateTimeError as exc:
            raise ValidationError(
                {"trigger_at": "trigger_at must include an explicit timezone"}
            ) from exc

        has_target_id = self.target_id is not None
        is_custom = self.target_type == ReminderTargetType.CUSTOM
        if is_custom and has_target_id:
            raise ValidationError({"target_id": "Custom reminders cannot reference a target"})
        if not is_custom and not has_target_id:
            raise ValidationError({"target_id": "Targeted reminders require target_id"})
        has_schedule = bool(self.schedule_anchor)
        if has_schedule != (self.offset_minutes is not None):
            raise ValidationError(
                {"offset_minutes": "Scheduled reminders require an anchor and non-negative offset"}
            )
        if self.status == ReminderStatus.SENT and self.sent_at is None:
            raise ValidationError({"sent_at": "Sent reminders require sent_at"})
        if self.status == ReminderStatus.FAILED and not self.failure_reason.strip():
            raise ValidationError({"failure_reason": "Failed reminders require a failure reason"})

    def can_transition_to(self, new_status: ReminderStatus | str) -> bool:
        try:
            normalized_status = ReminderStatus(new_status)
            current_status = ReminderStatus(self.status)
        except ValueError:
            return False
        return normalized_status in self.TRANSITIONS[current_status]

    def transition_to(
        self,
        new_status: ReminderStatus | str,
        *,
        occurred_at: datetime,
        failure_reason: str = "",
    ) -> None:
        try:
            normalized_status = ReminderStatus(new_status)
            occurred_at_utc = to_utc(occurred_at)
        except ValueError as exc:
            raise InvalidReminderTransitionError(str(exc)) from exc
        except NaiveDateTimeError as exc:
            raise InvalidReminderTransitionError(
                "occurred_at must include an explicit timezone"
            ) from exc

        if not self.can_transition_to(normalized_status):
            raise InvalidReminderTransitionError(
                f"Cannot transition reminder from {self.status} to {normalized_status}"
            )

        if normalized_status == ReminderStatus.QUEUED:
            if self.status == ReminderStatus.FAILED:
                self.retry_count += 1
            self.queued_at = occurred_at_utc
            self.failure_reason = ""
        elif normalized_status == ReminderStatus.SENT:
            self.sent_at = occurred_at_utc
            self.failure_reason = ""
        elif normalized_status == ReminderStatus.FAILED:
            normalized_reason = failure_reason.strip()
            if not normalized_reason:
                raise InvalidReminderTransitionError(
                    "A failure reason is required for failed reminders"
                )
            self.failure_reason = normalized_reason

        self.status = normalized_status
