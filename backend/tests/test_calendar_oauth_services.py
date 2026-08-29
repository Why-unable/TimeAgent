from datetime import UTC, datetime
from io import StringIO
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import override_settings

from apps.accounts.models import GuestAccount
from apps.integrations.calendar.capabilities import CalendarProviderCapabilities
from apps.integrations.calendar.dto import (
    ExternalCalendarContext,
    ExternalCalendarSummary,
    ExternalEvent,
    ExternalEventCreate,
    ExternalEventPage,
    ExternalEventQuery,
    ExternalEventUpdate,
)
from apps.integrations.calendar.exceptions import ExternalCalendarAuthenticationError
from apps.integrations.calendar.google_oauth import (
    GOOGLE_CALENDAR_READONLY_SCOPE,
    GoogleOAuthClient,
    GoogleOAuthTokens,
)
from apps.integrations.calendar.oauth_services import (
    CalendarCredentialCipher,
    CalendarCredentialService,
    CalendarOAuthService,
)
from apps.integrations.models import (
    CalendarOAuthCredential,
    CalendarOAuthState,
    CalendarSyncConnection,
)
from common.clock import FixedClock

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 8, 24, 4, 0, tzinfo=UTC)


class PrimaryCalendarProvider:
    provider_name = "google"

    def list_calendars(
        self, context: ExternalCalendarContext
    ) -> list[ExternalCalendarSummary]:
        del context
        return [
            ExternalCalendarSummary(
                external_id="account@example.test",
                name="Primary calendar",
                timezone="Asia/Shanghai",
                is_primary=True,
                read_only=True,
            )
        ]

    def get_capabilities(self) -> CalendarProviderCapabilities:
        return CalendarProviderCapabilities(read_calendars=True, read_events=True)

    def list_events(
        self, context: ExternalCalendarContext, query: ExternalEventQuery
    ) -> ExternalEventPage:
        raise AssertionError("Not needed by OAuth callback")

    def create_event(
        self,
        context: ExternalCalendarContext,
        event: ExternalEventCreate,
    ) -> ExternalEvent:
        del context, event
        raise AssertionError("read-only")

    def update_event(
        self,
        context: ExternalCalendarContext,
        external_event_id: str,
        event: ExternalEventUpdate,
    ) -> ExternalEvent:
        del context, external_event_id, event
        raise AssertionError("read-only")

    def cancel_event(
        self,
        context: ExternalCalendarContext,
        external_event_id: str,
    ) -> None:
        del context, external_event_id
        raise AssertionError("read-only")


class TokenRequester:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def __call__(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self.responses:
            raise AssertionError("Unexpected OAuth request")
        return httpx.Response(
            200,
            json=self.responses.pop(0),
            request=httpx.Request(method, url),
        )


def create_user(username: str = "oauth-user") -> User:
    return get_user_model().objects.create_user(username=username)


def oauth_client(requester: TokenRequester) -> GoogleOAuthClient:
    return GoogleOAuthClient(
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri="https://time.example/oauth/callback",
        requester=requester,
    )


def test_google_oauth_callback_encrypts_tokens_and_rejects_state_replay() -> None:
    user = create_user()
    clock = FixedClock(NOW)
    requester = TokenRequester(
        [
            {
                "access_token": "plain-access-token",
                "refresh_token": "plain-refresh-token",
                "expires_in": 3600,
                "scope": GOOGLE_CALENDAR_READONLY_SCOPE,
            }
        ]
    )
    client = oauth_client(requester)
    started = CalendarOAuthService.begin_google(user=user, oauth_client=client, clock=clock)
    state = parse_qs(urlparse(started.authorization_url).query)["state"][0]
    stored_state = CalendarOAuthState.objects.get(user=user)
    assert stored_state.state_digest != state
    assert len(stored_state.state_digest) == 64

    result = CalendarOAuthService.complete_google(
        state=state,
        code="authorization-code",
        oauth_client=client,
        provider_factory=lambda _token: PrimaryCalendarProvider(),
        clock=clock,
    )

    credential = CalendarOAuthCredential.objects.get(user=user)
    assert "plain-access-token" not in credential.encrypted_token_payload
    assert "plain-refresh-token" not in credential.encrypted_token_payload
    decrypted = CalendarCredentialCipher().decrypt(credential.encrypted_token_payload)
    assert decrypted.access_token == "plain-access-token"
    assert decrypted.refresh_token == "plain-refresh-token"
    assert credential.access_token_expires_at == datetime(2026, 8, 24, 5, 0, tzinfo=UTC)
    assert result.connection.provider_name == "google"
    assert result.connection.account_reference == "account@example.test"
    stored_state.refresh_from_db()
    assert stored_state.consumed_at == NOW

    with pytest.raises(ExternalCalendarAuthenticationError, match="invalid or expired"):
        CalendarOAuthService.complete_google(
            state=state,
            code="authorization-code",
            oauth_client=client,
            provider_factory=lambda _token: PrimaryCalendarProvider(),
            clock=clock,
        )
    assert len(requester.calls) == 1


def test_google_token_refresh_preserves_existing_refresh_token() -> None:
    user = create_user("oauth-refresh-user")
    connection = CalendarSyncConnection.objects.create(
        user=user,
        provider_name="google",
        account_reference="account@example.test",
        calendar_id="account@example.test",
        calendar_name="Primary",
        timezone="Asia/Shanghai",
    )
    clock = FixedClock(NOW)
    cipher = CalendarCredentialCipher()
    CalendarCredentialService.save_google_tokens(
        user=user,
        account_reference=connection.account_reference,
        tokens=GoogleOAuthTokens(
            access_token="expired-access",
            refresh_token="stable-refresh",
            expires_in_seconds=1,
            scopes=(GOOGLE_CALENDAR_READONLY_SCOPE,),
        ),
        cipher=cipher,
        clock=FixedClock(datetime(2026, 8, 24, 3, 0, tzinfo=UTC)),
    )
    requester = TokenRequester(
        [
            {
                "access_token": "refreshed-access",
                "expires_in": 3600,
                "scope": GOOGLE_CALENDAR_READONLY_SCOPE,
            }
        ]
    )

    access_token = CalendarCredentialService.access_token_for_connection(
        connection=connection,
        oauth_client=oauth_client(requester),
        cipher=cipher,
        clock=clock,
    )

    credential = CalendarOAuthCredential.objects.get(user=user)
    decrypted = cipher.decrypt(credential.encrypted_token_payload)
    assert access_token == "refreshed-access"
    assert decrypted.refresh_token == "stable-refresh"
    assert "stable-refresh" not in credential.encrypted_token_payload


@pytest.mark.parametrize(
    ("access_token", "expires_in_seconds"),
    [("", 3600), ("access", 0), ("access", -1)],
)
def test_google_credentials_reject_invalid_access_tokens(
    access_token: str,
    expires_in_seconds: int,
) -> None:
    user = create_user(f"invalid-token-{expires_in_seconds}")

    with pytest.raises(
        ExternalCalendarAuthenticationError,
        match="invalid access token",
    ):
        CalendarCredentialService.save_google_tokens(
            user=user,
            account_reference="account@example.test",
            tokens=GoogleOAuthTokens(
                access_token=access_token,
                refresh_token="refresh",
                expires_in_seconds=expires_in_seconds,
                scopes=(GOOGLE_CALENDAR_READONLY_SCOPE,),
            ),
            clock=FixedClock(NOW),
        )

    assert CalendarOAuthCredential.objects.filter(user=user).exists() is False


def test_disconnect_deletes_tokens_and_disables_connections() -> None:
    user = create_user("oauth-disconnect-user")
    connection = CalendarSyncConnection.objects.create(
        user=user,
        provider_name="google",
        account_reference="account@example.test",
        calendar_id="account@example.test",
        calendar_name="Primary",
        timezone="Asia/Shanghai",
    )
    CalendarCredentialService.save_google_tokens(
        user=user,
        account_reference=connection.account_reference,
        tokens=GoogleOAuthTokens(
            access_token="access",
            refresh_token="refresh",
            expires_in_seconds=3600,
            scopes=(GOOGLE_CALENDAR_READONLY_SCOPE,),
        ),
        clock=FixedClock(NOW),
    )

    CalendarOAuthService.disconnect_google_connection(
        user=user,
        connection_id=connection.id,
        clock=FixedClock(NOW),
    )

    connection.refresh_from_db()
    assert CalendarOAuthCredential.objects.filter(user=user).exists() is False
    assert connection.enabled is False
    assert connection.status == "disabled"
    assert connection.sync_cursor == ""


def test_guest_cannot_start_external_calendar_oauth() -> None:
    user = create_user("oauth-guest-user")
    GuestAccount.objects.create(
        user=user,
        expires_at=datetime(2026, 8, 25, 0, 0, tzinfo=UTC),
    )

    with pytest.raises(ExternalCalendarAuthenticationError, match="Guest accounts"):
        CalendarOAuthService.begin_google(
            user=user,
            oauth_client=oauth_client(TokenRequester([])),
            clock=FixedClock(NOW),
        )


def test_oauth_test_key_is_not_the_django_secret_key() -> None:
    assert settings.CALENDAR_OAUTH_FERNET_KEY
    assert settings.CALENDAR_OAUTH_FERNET_KEY != settings.SECRET_KEY


def test_rotation_command_reencrypts_with_primary_key_without_printing_tokens() -> None:
    user = create_user("oauth-rotation-user")
    old_key = Fernet.generate_key().decode("ascii")
    new_key = Fernet.generate_key().decode("ascii")
    old_cipher = CalendarCredentialCipher(old_key)
    credential = CalendarCredentialService.save_google_tokens(
        user=user,
        account_reference="rotation@example.test",
        tokens=GoogleOAuthTokens(
            access_token="rotation-access-token",
            refresh_token="rotation-refresh-token",
            expires_in_seconds=3600,
            scopes=(GOOGLE_CALENDAR_READONLY_SCOPE,),
        ),
        cipher=old_cipher,
        clock=FixedClock(NOW),
    )
    original_ciphertext = credential.encrypted_token_payload
    output = StringIO()

    with override_settings(
        CALENDAR_OAUTH_FERNET_KEY=new_key,
        CALENDAR_OAUTH_FERNET_OLD_KEYS=[old_key],
    ):
        call_command("rotate_calendar_oauth_credentials", stdout=output)

    credential.refresh_from_db()
    decrypted = CalendarCredentialCipher(new_key).decrypt(credential.encrypted_token_payload)
    assert credential.encrypted_token_payload != original_ciphertext
    assert decrypted.access_token == "rotation-access-token"
    assert decrypted.refresh_token == "rotation-refresh-token"
    assert "rotation-access-token" not in output.getvalue()
    assert "rotation-refresh-token" not in output.getvalue()
