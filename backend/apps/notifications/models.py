import uuid
from datetime import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from common.time import NaiveDateTimeError, to_utc


class NotificationSourceType(models.TextChoices):
    REMINDER = "reminder", "Reminder"
    BRIEFING = "briefing", "Briefing"
    SYSTEM = "system", "System"


class NotificationChannelType(models.TextChoices):
    CONSOLE = "console", "Console"
    EMAIL = "email", "Email"
    WEB_PUSH = "web_push", "Web push"


class NotificationDeliveryStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    QUEUED = "queued", "Queued"
    SENDING = "sending", "Sending"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class InvalidNotificationTransitionError(ValueError):
    pass


class NotificationDelivery(models.Model):
    TRANSITIONS = {
        NotificationDeliveryStatus.PENDING: frozenset(
            {NotificationDeliveryStatus.QUEUED, NotificationDeliveryStatus.CANCELLED}
        ),
        NotificationDeliveryStatus.QUEUED: frozenset(
            {NotificationDeliveryStatus.SENDING, NotificationDeliveryStatus.CANCELLED}
        ),
        NotificationDeliveryStatus.SENDING: frozenset(
            {NotificationDeliveryStatus.SENT, NotificationDeliveryStatus.FAILED}
        ),
        NotificationDeliveryStatus.FAILED: frozenset(
            {NotificationDeliveryStatus.QUEUED, NotificationDeliveryStatus.CANCELLED}
        ),
        NotificationDeliveryStatus.SENT: frozenset(),
        NotificationDeliveryStatus.CANCELLED: frozenset(),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_deliveries",
    )
    source_type = models.CharField(max_length=16, choices=NotificationSourceType.choices)
    source_id = models.UUIDField(null=True, blank=True)
    channel_type = models.CharField(max_length=16, choices=NotificationChannelType.choices)
    status = models.CharField(
        max_length=16,
        choices=NotificationDeliveryStatus.choices,
        default=NotificationDeliveryStatus.PENDING,
    )
    deduplication_key = models.CharField(max_length=255)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    payload = models.JSONField(default=dict, blank=True)
    scheduled_at = models.DateTimeField()
    queued_at = models.DateTimeField(null=True, blank=True)
    sending_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    provider_message_id = models.CharField(max_length=255, blank=True)
    failure_code = models.CharField(max_length=64, blank=True)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "deduplication_key"],
                name="notification_unique_user_dedup_key",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status=NotificationDeliveryStatus.PENDING)
                    | models.Q(status=NotificationDeliveryStatus.CANCELLED)
                    | models.Q(queued_at__isnull=False)
                ),
                name="notification_active_has_queued_at",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status__in=[
                            NotificationDeliveryStatus.PENDING,
                            NotificationDeliveryStatus.QUEUED,
                            NotificationDeliveryStatus.CANCELLED,
                        ]
                    )
                    | models.Q(sending_at__isnull=False)
                ),
                name="notification_attempt_has_sending_at",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=NotificationDeliveryStatus.SENT)
                    | models.Q(sent_at__isnull=False)
                ),
                name="notification_sent_has_timestamp",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=NotificationDeliveryStatus.FAILED)
                    | (
                        models.Q(failed_at__isnull=False)
                        & ~models.Q(failure_code="")
                        & ~models.Q(failure_reason="")
                    )
                ),
                name="notification_failed_has_details",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(source_type=NotificationSourceType.SYSTEM)
                    | models.Q(source_id__isnull=False)
                ),
                name="notification_business_source_has_id",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "scheduled_at"], name="notification_due_scan_idx"),
            models.Index(fields=["status", "next_retry_at"], name="notification_retry_scan_idx"),
            models.Index(fields=["user", "created_at"], name="notification_user_created_idx"),
            models.Index(
                fields=["user", "source_type", "source_id"],
                name="notification_user_source_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.channel_type}:{self.subject} ({self.status})"

    def clean(self) -> None:
        super().clean()
        self.deduplication_key = self.deduplication_key.strip()
        self.subject = self.subject.strip()
        if not self.deduplication_key:
            raise ValidationError({"deduplication_key": "Deduplication key cannot be blank"})
        if not self.subject:
            raise ValidationError({"subject": "Subject cannot be blank"})
        if not isinstance(self.payload, dict):
            raise ValidationError({"payload": "Payload must be an object"})
        try:
            self.scheduled_at = to_utc(self.scheduled_at)
        except NaiveDateTimeError as exc:
            raise ValidationError(
                {"scheduled_at": "scheduled_at must include an explicit timezone"}
            ) from exc

    def can_transition_to(self, new_status: NotificationDeliveryStatus | str) -> bool:
        try:
            current = NotificationDeliveryStatus(self.status)
            target = NotificationDeliveryStatus(new_status)
        except ValueError:
            return False
        return target in self.TRANSITIONS[current]

    def transition_to(
        self,
        new_status: NotificationDeliveryStatus | str,
        *,
        occurred_at: datetime,
        failure_code: str = "",
        failure_reason: str = "",
        next_retry_at: datetime | None = None,
        provider_message_id: str = "",
    ) -> None:
        try:
            target = NotificationDeliveryStatus(new_status)
            occurred_at = to_utc(occurred_at)
        except (ValueError, NaiveDateTimeError) as exc:
            raise InvalidNotificationTransitionError(str(exc)) from exc
        if not self.can_transition_to(target):
            raise InvalidNotificationTransitionError(
                f"Cannot transition notification delivery from {self.status} to {target}"
            )
        if target == NotificationDeliveryStatus.QUEUED:
            self.queued_at = occurred_at
            self.next_retry_at = None
            self.failure_code = ""
            self.failure_reason = ""
        elif target == NotificationDeliveryStatus.SENDING:
            self.sending_at = occurred_at
            self.attempt_count += 1
        elif target == NotificationDeliveryStatus.SENT:
            self.sent_at = occurred_at
            self.provider_message_id = provider_message_id[:255]
            self.failure_code = ""
            self.failure_reason = ""
            self.next_retry_at = None
        elif target == NotificationDeliveryStatus.FAILED:
            code = failure_code.strip()
            reason = failure_reason.strip()
            if not code or not reason:
                raise InvalidNotificationTransitionError(
                    "Failed deliveries require failure_code and failure_reason"
                )
            self.failed_at = occurred_at
            self.failure_code = code[:64]
            self.failure_reason = reason[:4000]
            self.next_retry_at = to_utc(next_retry_at) if next_retry_at is not None else None
        self.status = target


class NotificationPreference(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preference",
    )
    reminder_console_enabled = models.BooleanField(default=True)
    reminder_email_enabled = models.BooleanField(default=False)
    reminder_web_push_enabled = models.BooleanField(default=False)
    briefing_console_enabled = models.BooleanField(default=True)
    briefing_email_enabled = models.BooleanField(default=False)
    briefing_web_push_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user_id"]

    def __str__(self) -> str:
        return f"Notification preferences for user {self.user_id}"


class WebPushSubscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="web_push_subscriptions",
    )
    endpoint = models.URLField(max_length=2048, unique=True)
    p256dh = models.TextField()
    auth = models.TextField()
    user_agent = models.CharField(max_length=512, blank=True)
    enabled = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "id"]
        indexes = [models.Index(fields=["user", "enabled"], name="webpush_user_enabled_idx")]

    def __str__(self) -> str:
        return f"Web Push subscription {self.pk} for user {self.user_id}"

    def clean(self) -> None:
        super().clean()
        self.endpoint = self.endpoint.strip()
        self.p256dh = self.p256dh.strip()
        self.auth = self.auth.strip()
        if not self.endpoint or not self.p256dh or not self.auth:
            raise ValidationError("A push subscription requires endpoint, p256dh, and auth")
