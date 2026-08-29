from datetime import UTC, datetime
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.test import Client, override_settings

from apps.events.models import CalendarEvent
from apps.integrations.calendar.google_oauth import (
    GOOGLE_CALENDAR_READONLY_SCOPE,
    GoogleOAuthTokens,
)
from apps.integrations.calendar.oauth_services import CalendarCredentialService
from apps.integrations.models import (
    CalendarOAuthCredential,
    CalendarOAuthState,
    CalendarSyncConnection,
)
from common.clock import FixedClock

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 8, 24, 4, 0, tzinfo=UTC)


def create_user(username: str = "oauth-api-user") -> User:
    return get_user_model().objects.create_user(username=username)


def authenticated_client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def test_oauth_start_returns_google_url_without_exposing_server_secrets() -> None:
    user = create_user()
    response = authenticated_client(user).post(
        "/api/v1/integrations/calendar/oauth/google/start/"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["authorization_url"].startswith("https://accounts.google.com/")
    assert "test-google-client" in payload["authorization_url"]
    assert "test-google-secret" not in payload["authorization_url"]
    assert CalendarOAuthState.objects.filter(user=user).count() == 1


@override_settings(CALENDAR_OAUTH_FERNET_KEY="")
def test_oauth_start_fails_before_redirect_when_encryption_is_not_configured() -> None:
    user = create_user("oauth-api-missing-key")

    response = authenticated_client(user).post(
        "/api/v1/integrations/calendar/oauth/google/start/"
    )

    assert response.status_code == 503
    assert CalendarOAuthState.objects.filter(user=user).exists() is False


def test_oauth_callback_redirects_without_echoing_code_or_state() -> None:
    with patch(
        "apps.integrations.views.CalendarOAuthService.complete_google"
    ) as complete_google:
        response = Client().get(
            "/api/v1/integrations/calendar/oauth/google/callback/",
            {"code": "private-code", "state": "private-state"},
        )

    assert response.status_code == 302
    assert response.headers["Location"] == "/calendar?calendar_oauth=connected"
    assert "private-code" not in response.content.decode()
    assert "private-state" not in response.content.decode()
    complete_google.assert_called_once_with(
        state="private-state",
        code="private-code",
    )


def test_oauth_callback_denial_uses_fixed_failure_redirect() -> None:
    user = create_user("oauth-denial-user")
    started = authenticated_client(user).post(
        "/api/v1/integrations/calendar/oauth/google/start/"
    )
    state = parse_qs(urlparse(started.json()["authorization_url"]).query)["state"][0]
    with patch("apps.integrations.views.CalendarOAuthService.complete_google") as complete_google:
        response = Client().get(
            "/api/v1/integrations/calendar/oauth/google/callback/",
            {"error": "access_denied", "state": state},
        )

    assert response.status_code == 302
    assert response.headers["Location"] == "/calendar?calendar_oauth=failed"
    complete_google.assert_not_called()
    assert CalendarOAuthState.objects.get(user=user).consumed_at is not None


def test_manual_connection_api_rejects_forged_google_connection() -> None:
    user = create_user("oauth-api-forged-user")
    response = authenticated_client(user).post(
        "/api/v1/integrations/calendar/connections/",
        data={
            "provider_name": "google",
            "account_reference": "account@example.test",
            "calendar_id": "primary",
            "calendar_name": "Forged",
            "timezone": "Asia/Shanghai",
            "enabled": True,
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert CalendarSyncConnection.objects.filter(user=user).exists() is False


def test_disconnect_endpoint_is_user_scoped_and_deletes_credential() -> None:
    owner = create_user("oauth-api-disconnect-owner")
    other = create_user("oauth-api-disconnect-other")
    connection = CalendarSyncConnection.objects.create(
        user=owner,
        provider_name="google",
        account_reference="account@example.test",
        calendar_id="account@example.test",
        calendar_name="Primary",
        timezone="Asia/Shanghai",
    )
    CalendarCredentialService.save_google_tokens(
        user=owner,
        account_reference=connection.account_reference,
        tokens=GoogleOAuthTokens(
            access_token="access",
            refresh_token="refresh",
            expires_in_seconds=3600,
            scopes=(GOOGLE_CALENDAR_READONLY_SCOPE,),
        ),
        clock=FixedClock(NOW),
    )

    hidden = authenticated_client(other).delete(
        f"/api/v1/integrations/calendar/connections/{connection.id}/disconnect/"
    )
    disconnected = authenticated_client(owner).delete(
        f"/api/v1/integrations/calendar/connections/{connection.id}/disconnect/"
    )

    connection.refresh_from_db()
    assert hidden.status_code == 404
    assert disconnected.status_code == 204
    assert connection.enabled is False
    assert CalendarOAuthCredential.objects.filter(user=owner).exists() is False


def test_google_sync_api_uses_encrypted_credential_and_persists_scoped_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user("oauth-api-sync-user")
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
            access_token="encrypted-access",
            refresh_token="encrypted-refresh",
            expires_in_seconds=31_536_000,
            scopes=(GOOGLE_CALENDAR_READONLY_SCOPE,),
        ),
        clock=FixedClock(NOW),
    )
    calls: list[dict[str, object]] = []

    def google_request(method: str, url: str, **kwargs: object) -> httpx.Response:
        calls.append({"method": method, "url": url, **kwargs})
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "google-event-1",
                        "summary": "Google meeting",
                        "start": {"dateTime": "2026-08-24T09:00:00+08:00"},
                        "end": {"dateTime": "2026-08-24T10:00:00+08:00"},
                    }
                ],
                "nextSyncToken": "google-sync-1",
            },
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr("apps.integrations.calendar.providers.google.httpx.request", google_request)
    response = authenticated_client(user).post(
        f"/api/v1/integrations/calendar/connections/{connection.id}/sync/",
        data={
            "starts_at_or_after": "2026-08-24T00:00:00Z",
            "starts_before": "2026-08-25T00:00:00Z",
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["created_count"] == 1
    event = CalendarEvent.objects.get(user=user, external_id="google-event-1")
    assert event.source == "google"
    assert event.external_account_reference == "account@example.test"
    assert event.external_calendar_id == "account@example.test"
    headers = calls[0]["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer encrypted-access"
