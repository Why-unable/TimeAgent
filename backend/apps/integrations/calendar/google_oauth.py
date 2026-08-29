from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from django.conf import settings

from apps.integrations.calendar.exceptions import (
    ExternalCalendarAuthenticationError,
    ExternalCalendarNotConfigured,
    ExternalCalendarRateLimitError,
    ExternalCalendarTemporaryError,
)

GOOGLE_CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
GoogleTokenRequester = Callable[..., httpx.Response]


@dataclass(frozen=True, slots=True)
class GoogleOAuthTokens:
    access_token: str
    refresh_token: str
    expires_in_seconds: int
    scopes: tuple[str, ...]


class GoogleOAuthClient:
    authorization_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
        requester: GoogleTokenRequester | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._client_id = (
            client_id if client_id is not None else settings.GOOGLE_CALENDAR_CLIENT_ID
        ).strip()
        self._client_secret = (
            client_secret if client_secret is not None else settings.GOOGLE_CALENDAR_CLIENT_SECRET
        ).strip()
        self._redirect_uri = (
            redirect_uri if redirect_uri is not None else settings.GOOGLE_CALENDAR_REDIRECT_URI
        ).strip()
        self._requester = requester or httpx.request
        self._timeout_seconds = timeout_seconds
        if not self._client_id or not self._client_secret or not self._redirect_uri:
            raise ExternalCalendarNotConfigured("Google Calendar OAuth is not configured")

    def build_authorization_url(self, *, state: str) -> str:
        return f"{self.authorization_url}?{urlencode(self.authorization_params(state=state))}"

    def authorization_params(self, *, state: str) -> dict[str, str]:
        if not state.strip():
            raise ValueError("OAuth state cannot be blank")
        return {
            "access_type": "offline",
            "client_id": self._client_id,
            "include_granted_scopes": "true",
            "prompt": "consent",
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_CALENDAR_READONLY_SCOPE,
            "state": state,
        }

    def exchange_code(self, *, code: str) -> GoogleOAuthTokens:
        if not code.strip():
            raise ExternalCalendarAuthenticationError("Google authorization code is missing")
        return self._request_tokens(
            {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self._redirect_uri,
            }
        )

    def refresh(self, *, refresh_token: str) -> GoogleOAuthTokens:
        if not refresh_token.strip():
            raise ExternalCalendarAuthenticationError("Google refresh token is unavailable")
        return self._request_tokens(
            {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
        )

    def _request_tokens(self, data: Mapping[str, str]) -> GoogleOAuthTokens:
        try:
            response = self._requester(
                "POST",
                self.token_url,
                headers={"Accept": "application/json"},
                data=data,
                timeout=self._timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ExternalCalendarTemporaryError("Google OAuth request timed out") from exc
        except httpx.RequestError as exc:
            raise ExternalCalendarTemporaryError("Google OAuth is unavailable") from exc
        if response.status_code in {400, 401, 403}:
            raise ExternalCalendarAuthenticationError("Google OAuth authorization failed")
        if response.status_code == 429:
            raise ExternalCalendarRateLimitError("Google OAuth rate limit exceeded")
        if response.status_code >= 500:
            raise ExternalCalendarTemporaryError("Google OAuth is temporarily unavailable")
        if response.is_error:
            raise ExternalCalendarAuthenticationError("Google OAuth authorization failed")
        payload = self._json_object(response)
        access_token = self._text(payload, "access_token")
        if not access_token:
            raise ExternalCalendarAuthenticationError("Google OAuth returned no access token")
        refresh_token = self._text(payload, "refresh_token")
        expires_in = payload.get("expires_in", 3600)
        if not isinstance(expires_in, int) or expires_in <= 0:
            raise ExternalCalendarAuthenticationError("Google OAuth returned invalid expiry")
        scope_text = self._text(payload, "scope") or GOOGLE_CALENDAR_READONLY_SCOPE
        scopes = tuple(sorted({scope for scope in scope_text.split() if scope}))
        return GoogleOAuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in_seconds=expires_in,
            scopes=scopes,
        )

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ExternalCalendarTemporaryError("Google OAuth returned malformed JSON") from exc
        if not isinstance(payload, dict):
            raise ExternalCalendarTemporaryError("Google OAuth returned malformed JSON")
        return payload

    @staticmethod
    def _text(payload: Mapping[str, Any], key: str) -> str:
        value = payload.get(key)
        return value.strip() if isinstance(value, str) else ""
