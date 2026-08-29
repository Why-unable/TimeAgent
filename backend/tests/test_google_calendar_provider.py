from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from apps.integrations.calendar.dto import (
    ExternalCalendarContext,
    ExternalEvent,
    ExternalEventQuery,
    ExternalEventTombstone,
)
from apps.integrations.calendar.exceptions import (
    ExternalCalendarRateLimitError,
    ExternalCalendarTemporaryError,
)
from apps.integrations.calendar.google_oauth import (
    GOOGLE_CALENDAR_READONLY_SCOPE,
    GoogleOAuthClient,
)
from apps.integrations.calendar.providers.google import GoogleCalendarProvider

START = datetime(2026, 8, 24, 0, 0, tzinfo=UTC)
END = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)


class ScriptedRequester:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def __call__(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self.responses:
            raise AssertionError("Unexpected HTTP request")
        response = self.responses.pop(0)
        if response.request is None:
            response.request = httpx.Request(method, url)
        return response


def response(status_code: int, payload: Mapping[str, Any]) -> httpx.Response:
    return httpx.Response(status_code, json=dict(payload), request=httpx.Request("GET", "https://x"))


def context() -> ExternalCalendarContext:
    return ExternalCalendarContext(
        account_reference="account@example.test",
        timezone="Asia/Shanghai",
    )


def query(*, sync_cursor: str = "") -> ExternalEventQuery:
    return ExternalEventQuery(
        calendar_id="primary@example.test",
        starts_at_or_after=START,
        starts_before=END,
        sync_cursor=sync_cursor,
    )


def test_google_provider_lists_paginated_calendars() -> None:
    requester = ScriptedRequester(
        [
            response(
                200,
                {
                    "items": [
                        {
                            "id": "primary@example.test",
                            "summary": "Primary",
                            "timeZone": "Asia/Shanghai",
                            "primary": True,
                            "accessRole": "owner",
                        }
                    ],
                    "nextPageToken": "page-2",
                },
            ),
            response(
                200,
                {
                    "items": [
                        {
                            "id": "team@example.test",
                            "summary": "Team",
                            "accessRole": "reader",
                        }
                    ]
                },
            ),
        ]
    )
    provider = GoogleCalendarProvider("access-token", requester=requester)

    calendars = provider.list_calendars(context())

    assert [calendar.external_id for calendar in calendars] == [
        "primary@example.test",
        "team@example.test",
    ]
    assert calendars[0].is_primary is True
    assert calendars[0].read_only is True
    assert calendars[1].timezone == "Asia/Shanghai"
    assert calendars[1].read_only is True
    assert requester.calls[1]["params"]["pageToken"] == "page-2"


def test_google_provider_normalizes_paginated_timed_all_day_and_deleted_events() -> None:
    requester = ScriptedRequester(
        [
            response(
                200,
                {
                    "items": [
                        {
                            "id": "timed-1",
                            "summary": "Review",
                            "status": "confirmed",
                            "start": {
                                "dateTime": "2026-08-24T09:00:00+08:00",
                                "timeZone": "Asia/Shanghai",
                            },
                            "end": {
                                "dateTime": "2026-08-24T10:00:00+08:00",
                                "timeZone": "Asia/Shanghai",
                            },
                        }
                    ],
                    "nextPageToken": "page-2",
                },
            ),
            response(
                200,
                {
                    "items": [
                        {
                            "id": "all-day-1",
                            "summary": "Holiday",
                            "start": {"date": "2026-08-25"},
                            "end": {"date": "2026-08-26"},
                        },
                        {"id": "deleted-1", "status": "cancelled"},
                    ],
                    "nextSyncToken": "sync-2",
                },
            ),
        ]
    )
    provider = GoogleCalendarProvider("access-token", requester=requester)

    page = provider.list_events(context(), query())

    assert page.next_sync_cursor == "sync-2"
    assert len(page.events) == 3
    timed = page.events[0]
    all_day = page.events[1]
    deleted = page.events[2]
    assert isinstance(timed, ExternalEvent)
    assert timed.starts_at == datetime(2026, 8, 24, 1, 0, tzinfo=UTC)
    assert isinstance(all_day, ExternalEvent)
    assert all_day.starts_at == datetime(2026, 8, 24, 16, 0, tzinfo=UTC)
    assert all_day.ends_at == datetime(2026, 8, 25, 16, 0, tzinfo=UTC)
    assert isinstance(deleted, ExternalEventTombstone)
    first_params = requester.calls[0]["params"]
    assert first_params["timeMin"] == "2026-08-24T00:00:00Z"
    assert first_params["timeMax"] == "2026-08-26T00:00:00Z"
    assert "syncToken" not in first_params
    assert requester.calls[1]["params"]["pageToken"] == "page-2"


def test_google_provider_resets_expired_sync_token_once() -> None:
    requester = ScriptedRequester(
        [
            response(410, {"error": {"message": "token expired"}}),
            response(200, {"items": [], "nextSyncToken": "replacement-token"}),
        ]
    )
    provider = GoogleCalendarProvider("access-token", requester=requester)

    page = provider.list_events(context(), query(sync_cursor="expired-token"))

    assert page.cursor_was_reset is True
    assert page.next_sync_cursor == "replacement-token"
    incremental_params = requester.calls[0]["params"]
    replacement_params = requester.calls[1]["params"]
    assert incremental_params["syncToken"] == "expired-token"
    assert "timeMin" not in incremental_params
    assert "syncToken" not in replacement_params
    assert replacement_params["timeMin"] == "2026-08-24T00:00:00Z"


def test_google_provider_sanitizes_rate_limit_error() -> None:
    requester = ScriptedRequester(
        [response(429, {"error": {"message": "token=private-access-token"}})]
    )
    provider = GoogleCalendarProvider("private-access-token", requester=requester)

    with pytest.raises(ExternalCalendarRateLimitError) as error:
        provider.list_calendars(context())

    assert "private-access-token" not in str(error.value)


def test_google_provider_sanitizes_invalid_calendar_data() -> None:
    requester = ScriptedRequester(
        [
            response(
                200,
                {
                    "items": [
                        {
                            "id": "primary@example.test",
                            "summary": "Primary",
                            "timeZone": "Private/Invalid-Timezone",
                            "primary": True,
                        }
                    ]
                },
            )
        ]
    )
    provider = GoogleCalendarProvider("access-token", requester=requester)

    with pytest.raises(
        ExternalCalendarTemporaryError,
        match="invalid calendar data",
    ) as error:
        provider.list_calendars(context())

    assert "Private/Invalid-Timezone" not in str(error.value)


def test_google_provider_sanitizes_invalid_event_data() -> None:
    requester = ScriptedRequester(
        [
            response(
                200,
                {
                    "items": [
                        {
                            "id": "invalid-date",
                            "summary": "Invalid",
                            "start": {"date": "private-invalid-date"},
                            "end": {"date": "2026-08-26"},
                        }
                    ],
                    "nextSyncToken": "sync-2",
                },
            )
        ]
    )
    provider = GoogleCalendarProvider("access-token", requester=requester)

    with pytest.raises(
        ExternalCalendarTemporaryError,
        match="invalid event data",
    ) as error:
        provider.list_events(context(), query())

    assert "private-invalid-date" not in str(error.value)


def test_google_oauth_client_builds_read_only_offline_authorization_url() -> None:
    client = GoogleOAuthClient(
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri="https://time.example/api/callback",
        requester=ScriptedRequester([]),
    )

    params = parse_qs(urlparse(client.build_authorization_url(state="opaque-state")).query)

    assert params["scope"] == [GOOGLE_CALENDAR_READONLY_SCOPE]
    assert params["access_type"] == ["offline"]
    assert params["include_granted_scopes"] == ["true"]
    assert params["state"] == ["opaque-state"]


def test_google_oauth_client_exchanges_and_refreshes_tokens() -> None:
    requester = ScriptedRequester(
        [
            response(
                200,
                {
                    "access_token": "access-1",
                    "refresh_token": "refresh-1",
                    "expires_in": 3600,
                    "scope": GOOGLE_CALENDAR_READONLY_SCOPE,
                },
            ),
            response(200, {"access_token": "access-2", "expires_in": 1800}),
        ]
    )
    client = GoogleOAuthClient(
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri="https://time.example/api/callback",
        requester=requester,
    )

    exchanged = client.exchange_code(code="authorization-code")
    refreshed = client.refresh(refresh_token=exchanged.refresh_token)

    assert exchanged.access_token == "access-1"
    assert exchanged.refresh_token == "refresh-1"
    assert refreshed.access_token == "access-2"
    assert refreshed.refresh_token == ""
    assert requester.calls[0]["data"]["grant_type"] == "authorization_code"
    assert requester.calls[1]["data"]["grant_type"] == "refresh_token"
