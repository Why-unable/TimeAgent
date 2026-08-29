import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.preferences.models import validate_iana_timezone


class CalendarSyncStatus(models.TextChoices):
    READY = "ready", "Ready"
    ERROR = "error", "Error"
    DISABLED = "disabled", "Disabled"


class CalendarSyncConnection(models.Model):
    """Read-only external calendar identity and incremental-sync state."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="calendar_sync_connections",
    )
    provider_name = models.CharField(max_length=64)
    account_reference = models.CharField(max_length=255)
    calendar_id = models.CharField(max_length=255)
    calendar_name = models.CharField(max_length=255)
    timezone = models.CharField(max_length=64, validators=[validate_iana_timezone])
    enabled = models.BooleanField(default=True)
    sync_cursor = models.CharField(max_length=2048, blank=True)
    status = models.CharField(
        max_length=16,
        choices=CalendarSyncStatus.choices,
        default=CalendarSyncStatus.READY,
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["provider_name", "calendar_name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "provider_name", "account_reference", "calendar_id"],
                name="calendar_sync_connection_identity_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "enabled", "status"],
                name="calendar_sync_user_status_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider_name}: {self.calendar_name}"

    def clean(self) -> None:
        super().clean()
        for field_name in (
            "provider_name",
            "account_reference",
            "calendar_id",
            "calendar_name",
        ):
            value = getattr(self, field_name).strip()
            if not value:
                raise ValidationError({field_name: f"{field_name} cannot be blank"})
            setattr(self, field_name, value)
        self.sync_cursor = self.sync_cursor.strip()
        self.last_error = self.last_error.strip()
        if not self.enabled:
            self.status = CalendarSyncStatus.DISABLED
        elif self.status == CalendarSyncStatus.DISABLED:
            self.status = CalendarSyncStatus.READY


class CalendarOAuthCredential(models.Model):
    """Encrypted OAuth token payload for one user/provider account."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="calendar_oauth_credentials",
    )
    provider_name = models.CharField(max_length=64)
    account_reference = models.CharField(max_length=255)
    encrypted_token_payload = models.TextField()
    access_token_expires_at = models.DateTimeField(null=True, blank=True)
    scopes = models.JSONField(default=list, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_refreshed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "provider_name", "account_reference"],
                name="calendar_oauth_credential_identity_uniq",
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider_name} credential {self.pk}"

    def clean(self) -> None:
        super().clean()
        self.provider_name = self.provider_name.strip()
        self.account_reference = self.account_reference.strip()
        self.encrypted_token_payload = self.encrypted_token_payload.strip()
        errors: dict[str, str] = {}
        if not self.provider_name:
            errors["provider_name"] = "provider_name cannot be blank"
        if not self.account_reference:
            errors["account_reference"] = "account_reference cannot be blank"
        if not self.encrypted_token_payload:
            errors["encrypted_token_payload"] = "encrypted_token_payload cannot be blank"
        if not isinstance(self.scopes, list) or any(
            not isinstance(scope, str) or not scope.strip() for scope in self.scopes
        ):
            errors["scopes"] = "scopes must be a list of non-empty strings"
        if errors:
            raise ValidationError(errors)
        self.scopes = sorted({scope.strip() for scope in self.scopes})


class CalendarOAuthState(models.Model):
    """Short-lived, one-time OAuth state; only its digest is persisted."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="calendar_oauth_states",
    )
    provider_name = models.CharField(max_length=64)
    state_digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["provider_name", "expires_at", "consumed_at"],
                name="cal_oauth_state_lookup_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider_name} OAuth state {self.pk}"

    def clean(self) -> None:
        super().clean()
        self.provider_name = self.provider_name.strip()
        self.state_digest = self.state_digest.strip().lower()
        errors: dict[str, str] = {}
        if not self.provider_name:
            errors["provider_name"] = "provider_name cannot be blank"
        if len(self.state_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.state_digest
        ):
            errors["state_digest"] = "state_digest must be a SHA-256 hex digest"
        if errors:
            raise ValidationError(errors)
