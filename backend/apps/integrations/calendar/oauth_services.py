from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)
from pydantic import (
    ValidationError as PydanticValidationError,
)

from apps.accounts.services import GuestAccountPolicyService
from apps.integrations.calendar.contracts import ExternalCalendarProvider
from apps.integrations.calendar.dto import ExternalCalendarContext, ExternalCalendarSummary
from apps.integrations.calendar.exceptions import (
    ExternalCalendarAuthenticationError,
    ExternalCalendarNotConfigured,
)
from apps.integrations.calendar.google_oauth import (
    GOOGLE_CALENDAR_READONLY_SCOPE,
    GoogleOAuthClient,
    GoogleOAuthTokens,
)
from apps.integrations.calendar.providers.google import GoogleCalendarProvider
from apps.integrations.calendar.sync_services import CalendarSyncService
from apps.integrations.models import (
    CalendarOAuthCredential,
    CalendarOAuthState,
    CalendarSyncConnection,
    CalendarSyncStatus,
)
from common.clock import Clock, SystemClock

ProviderFactory = Callable[[str], ExternalCalendarProvider]


class EncryptedTokenPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    access_token: str = Field(min_length=1)
    refresh_token: str = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class CalendarOAuthStartResult:
    authorization_url: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class CalendarOAuthCallbackResult:
    user: User
    connection: CalendarSyncConnection


class CalendarCredentialCipher:
    def __init__(self, key: str | None = None) -> None:
        configured_key = key if key is not None else settings.CALENDAR_OAUTH_FERNET_KEY
        if not configured_key.strip():
            raise ExternalCalendarNotConfigured(
                "Calendar OAuth credential encryption is not configured"
            )
        try:
            keys = [configured_key.strip()]
            if key is None:
                keys.extend(settings.CALENDAR_OAUTH_FERNET_OLD_KEYS)
            self._fernet = MultiFernet(
                [Fernet(candidate.encode("ascii")) for candidate in keys]
            )
        except (UnicodeEncodeError, ValueError) as exc:
            raise ExternalCalendarNotConfigured(
                "Calendar OAuth credential encryption key is invalid"
            ) from exc

    def encrypt(self, payload: EncryptedTokenPayload) -> str:
        serialized = json.dumps(
            payload.model_dump(mode="json"),
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return self._fernet.encrypt(serialized).decode("ascii")

    def decrypt(self, ciphertext: str) -> EncryptedTokenPayload:
        try:
            raw = self._fernet.decrypt(ciphertext.encode("ascii"))
            payload = json.loads(raw.decode("utf-8"))
            return EncryptedTokenPayload.model_validate(payload)
        except (
            InvalidToken,
            UnicodeDecodeError,
            UnicodeEncodeError,
            ValueError,
            PydanticValidationError,
        ) as exc:
            raise ExternalCalendarAuthenticationError(
                "Stored calendar credential cannot be decrypted"
            ) from exc

    def rotate(self, ciphertext: str) -> str:
        try:
            return self._fernet.rotate(ciphertext.encode("ascii")).decode("ascii")
        except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError, ValueError) as exc:
            raise ExternalCalendarAuthenticationError(
                "Stored calendar credential cannot be re-encrypted"
            ) from exc


class CalendarCredentialService:
    refresh_skew = timedelta(seconds=60)

    @staticmethod
    @transaction.atomic
    def save_google_tokens(
        *,
        user: User,
        account_reference: str,
        tokens: GoogleOAuthTokens,
        cipher: CalendarCredentialCipher | None = None,
        clock: Clock | None = None,
    ) -> CalendarOAuthCredential:
        if user.pk is None:
            raise ValueError("Calendar credential user must be persisted")
        account_reference = account_reference.strip()
        if not account_reference:
            raise ValueError("Calendar credential account reference cannot be blank")
        access_token = tokens.access_token.strip()
        if not access_token or tokens.expires_in_seconds <= 0:
            raise ExternalCalendarAuthenticationError(
                "Google returned an invalid access token"
            )
        token_cipher = cipher or CalendarCredentialCipher()
        now = (clock or SystemClock()).now_utc()
        credential = CalendarOAuthCredential.objects.select_for_update().filter(
            user=user,
            provider_name="google",
            account_reference=account_reference,
        ).first()
        refresh_token = tokens.refresh_token.strip()
        if not refresh_token and credential is not None:
            refresh_token = token_cipher.decrypt(
                credential.encrypted_token_payload
            ).refresh_token
        if not refresh_token:
            raise ExternalCalendarAuthenticationError(
                "Google did not return a refresh token; reconnect with consent"
            )
        encrypted_payload = token_cipher.encrypt(
            EncryptedTokenPayload(
                access_token=access_token,
                refresh_token=refresh_token,
            )
        )
        expires_at = now + timedelta(seconds=tokens.expires_in_seconds)
        if credential is None:
            credential = CalendarOAuthCredential(
                user=user,
                provider_name="google",
                account_reference=account_reference,
            )
        credential.encrypted_token_payload = encrypted_payload
        credential.access_token_expires_at = expires_at
        credential.scopes = list(tokens.scopes)
        credential.revoked_at = None
        credential.last_refreshed_at = now
        credential.full_clean()
        credential.save()
        return credential

    @staticmethod
    def access_token_for_connection(
        *,
        connection: CalendarSyncConnection,
        oauth_client: GoogleOAuthClient | None = None,
        cipher: CalendarCredentialCipher | None = None,
        clock: Clock | None = None,
    ) -> str:
        if connection.provider_name != "google":
            raise ValueError("Credential lookup only supports Google connections")
        token_cipher = cipher or CalendarCredentialCipher()
        current_clock = clock or SystemClock()
        credential = CalendarOAuthCredential.objects.filter(
            user=connection.user,
            provider_name="google",
            account_reference=connection.account_reference,
        ).first()
        if credential is None or credential.revoked_at is not None:
            raise ExternalCalendarAuthenticationError("Google Calendar is disconnected")
        payload = token_cipher.decrypt(credential.encrypted_token_payload)
        expires_at = credential.access_token_expires_at
        refresh_boundary = current_clock.now_utc() + CalendarCredentialService.refresh_skew
        if expires_at is None or expires_at > refresh_boundary:
            return payload.access_token
        refreshed = (oauth_client or GoogleOAuthClient()).refresh(
            refresh_token=payload.refresh_token
        )
        updated = CalendarCredentialService.save_google_tokens(
            user=connection.user,
            account_reference=connection.account_reference,
            tokens=refreshed,
            cipher=token_cipher,
            clock=current_clock,
        )
        return token_cipher.decrypt(updated.encrypted_token_payload).access_token

    @staticmethod
    @transaction.atomic
    def rotate_encryption(
        *,
        cipher: CalendarCredentialCipher | None = None,
    ) -> int:
        token_cipher = cipher or CalendarCredentialCipher()
        credentials = list(CalendarOAuthCredential.objects.select_for_update().all())
        for credential in credentials:
            credential.encrypted_token_payload = token_cipher.rotate(
                credential.encrypted_token_payload
            )
            credential.full_clean()
            credential.save(update_fields=["encrypted_token_payload", "updated_at"])
        return len(credentials)


class CalendarOAuthService:
    @staticmethod
    @transaction.atomic
    def begin_google(
        *,
        user: User,
        oauth_client: GoogleOAuthClient | None = None,
        clock: Clock | None = None,
    ) -> CalendarOAuthStartResult:
        if user.pk is None:
            raise ValueError("OAuth user must be persisted")
        if GuestAccountPolicyService.is_guest(user):
            raise ExternalCalendarAuthenticationError(
                "Guest accounts cannot connect external calendars"
            )
        client = oauth_client or GoogleOAuthClient()
        CalendarCredentialCipher()
        current_clock = clock or SystemClock()
        now = current_clock.now_utc()
        CalendarOAuthState.objects.filter(user=user, provider_name="google").filter(
            Q(consumed_at__isnull=False) | Q(expires_at__lte=now)
        ).delete()
        raw_state = secrets.token_urlsafe(32)
        state_ttl_seconds = settings.CALENDAR_OAUTH_STATE_TTL_SECONDS
        if state_ttl_seconds <= 0:
            raise ExternalCalendarNotConfigured("Calendar OAuth state TTL is invalid")
        expires_at = now + timedelta(seconds=state_ttl_seconds)
        oauth_state = CalendarOAuthState(
            user=user,
            provider_name="google",
            state_digest=CalendarOAuthService._state_digest(raw_state),
            expires_at=expires_at,
        )
        oauth_state.full_clean()
        oauth_state.save(force_insert=True)
        authorization_url = client.build_authorization_url(state=raw_state)
        return CalendarOAuthStartResult(
            authorization_url=authorization_url,
            expires_at=expires_at,
        )

    @staticmethod
    def complete_google(
        *,
        state: str,
        code: str,
        oauth_client: GoogleOAuthClient | None = None,
        provider_factory: ProviderFactory | None = None,
        cipher: CalendarCredentialCipher | None = None,
        clock: Clock | None = None,
    ) -> CalendarOAuthCallbackResult:
        current_clock = clock or SystemClock()
        user = CalendarOAuthService._consume_state(
            state=state,
            provider_name="google",
            clock=current_clock,
        )
        client = oauth_client or GoogleOAuthClient()
        tokens = client.exchange_code(code=code)
        if GOOGLE_CALENDAR_READONLY_SCOPE not in tokens.scopes:
            raise ExternalCalendarAuthenticationError(
                "Google did not grant read-only calendar access"
            )
        provider = (
            provider_factory(tokens.access_token)
            if provider_factory is not None
            else GoogleCalendarProvider(tokens.access_token)
        )
        calendars = provider.list_calendars(
            ExternalCalendarContext(
                account_reference="oauth-pending",
                timezone=CalendarOAuthService._user_timezone(user),
            )
        )
        primary = CalendarOAuthService._primary_calendar(calendars)
        account_reference = primary.external_id
        connection = CalendarOAuthService._persist_google_connection(
            user=user,
            account_reference=account_reference,
            primary=primary,
            tokens=tokens,
            cipher=cipher,
            clock=current_clock,
        )
        return CalendarOAuthCallbackResult(user=user, connection=connection)

    @staticmethod
    def reject_google(*, state: str, clock: Clock | None = None) -> None:
        CalendarOAuthService._consume_state(
            state=state,
            provider_name="google",
            clock=clock or SystemClock(),
        )

    @staticmethod
    @transaction.atomic
    def _persist_google_connection(
        *,
        user: User,
        account_reference: str,
        primary: ExternalCalendarSummary,
        tokens: GoogleOAuthTokens,
        cipher: CalendarCredentialCipher | None,
        clock: Clock,
    ) -> CalendarSyncConnection:
        CalendarCredentialService.save_google_tokens(
            user=user,
            account_reference=account_reference,
            tokens=tokens,
            cipher=cipher,
            clock=clock,
        )
        return CalendarSyncService.upsert_connection(
            user=user,
            provider_name="google",
            account_reference=account_reference,
            calendar_id=primary.external_id,
            calendar_name=primary.name,
            timezone_name=primary.timezone,
            enabled=True,
        )

    @staticmethod
    @transaction.atomic
    def disconnect_google_connection(
        *,
        user: User,
        connection_id: UUID,
        clock: Clock | None = None,
    ) -> None:
        connection = CalendarSyncConnection.objects.select_for_update().filter(
            pk=connection_id,
            user=user,
            provider_name="google",
        ).first()
        if connection is None:
            raise CalendarSyncConnection.DoesNotExist
        CalendarOAuthCredential.objects.filter(
            user=user,
            provider_name="google",
            account_reference=connection.account_reference,
        ).delete()
        CalendarSyncConnection.objects.filter(
            user=user,
            provider_name="google",
            account_reference=connection.account_reference,
        ).update(
            enabled=False,
            status=CalendarSyncStatus.DISABLED,
            sync_cursor="",
            last_error="",
            updated_at=(clock or SystemClock()).now_utc(),
        )

    @staticmethod
    @transaction.atomic
    def _consume_state(*, state: str, provider_name: str, clock: Clock) -> User:
        digest = CalendarOAuthService._state_digest(state)
        oauth_state = CalendarOAuthState.objects.select_for_update().filter(
            provider_name=provider_name,
            state_digest=digest,
        ).first()
        now = clock.now_utc()
        if (
            oauth_state is None
            or oauth_state.consumed_at is not None
            or oauth_state.expires_at <= now
        ):
            raise ExternalCalendarAuthenticationError("OAuth state is invalid or expired")
        oauth_state.consumed_at = now
        oauth_state.save(update_fields=["consumed_at"])
        return oauth_state.user

    @staticmethod
    def _state_digest(state: str) -> str:
        if not state.strip():
            raise ExternalCalendarAuthenticationError("OAuth state is invalid or expired")
        return hashlib.sha256(state.encode("utf-8")).hexdigest()

    @staticmethod
    def _primary_calendar(
        calendars: list[ExternalCalendarSummary],
    ) -> ExternalCalendarSummary:
        primary = next((calendar for calendar in calendars if calendar.is_primary), None)
        if primary is None:
            raise ExternalCalendarAuthenticationError(
                "Google account has no accessible primary calendar"
            )
        return primary

    @staticmethod
    def _user_timezone(user: User) -> str:
        preference = getattr(user, "preference", None)
        timezone_name = getattr(preference, "timezone", "")
        return timezone_name or settings.DEFAULT_USER_TIMEZONE
