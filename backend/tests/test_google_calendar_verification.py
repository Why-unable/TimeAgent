import json
from collections.abc import Mapping
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection as database_connection

from apps.integrations.calendar.providers.google import GoogleCalendarProvider
from apps.integrations.calendar.verification import GoogleCalendarVerificationService
from apps.integrations.models import CalendarSyncConnection
from common.clock import FixedClock

pytestmark = pytest.mark.django_db

START = datetime(2026, 8, 24, 0, 0, tzinfo=UTC)
END = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)


class ScriptedRequester:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses

    def __call__(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        del kwargs
        if not self.responses:
            raise AssertionError("Unexpected Google request")
        response = self.responses.pop(0)
        if response.request is None:
            response.request = httpx.Request(method, url)
        return response


def response(status_code: int, payload: Mapping[str, Any]) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=dict(payload),
        request=httpx.Request("GET", "https://google.example.test"),
    )


def create_connection(username: str) -> tuple[User, CalendarSyncConnection]:
    user = get_user_model().objects.create_user(username=username)
    connection = CalendarSyncConnection.objects.create(
        user=user,
        provider_name="google",
        account_reference="private-account@example.test",
        calendar_id="private-calendar@example.test",
        calendar_name="Private calendar",
        timezone="Asia/Shanghai",
        sync_cursor="expired-private-cursor",
    )
    return user, connection


def test_google_calendar_verification_reports_pagination_and_cursor_reset() -> None:
    user, connection = create_connection("google-verification")
    provider = GoogleCalendarProvider(
        "private-access-token",
        requester=ScriptedRequester(
            [
                response(
                    200,
                    {
                        "items": [
                            {
                                "id": "private-calendar@example.test",
                                "summary": "Primary",
                                "timeZone": "Asia/Shanghai",
                                "primary": True,
                            }
                        ],
                        "nextPageToken": "private-calendar-page",
                    },
                ),
                response(200, {"items": []}),
                response(410, {"error": {"message": "private cursor expired"}}),
                response(
                    200,
                    {
                        "items": [
                            {
                                "id": "event-1",
                                "summary": "Focus",
                                "start": {"dateTime": "2026-08-24T09:00:00+08:00"},
                                "end": {"dateTime": "2026-08-24T10:00:00+08:00"},
                            }
                        ],
                        "nextPageToken": "private-event-page",
                    },
                ),
                response(200, {"items": [], "nextSyncToken": "private-new-cursor"}),
            ]
        ),
    )
    monotonic_values = iter([10.0, 10.125])

    report = GoogleCalendarVerificationService.verify(
        user=user,
        connection_id=connection.id,
        starts_at=START,
        starts_before=END,
        provider=provider,
        clock=FixedClock(END),
        monotonic=lambda: next(monotonic_values),
    )

    assert report.status == "pass"
    assert report.duration_ms == 125
    assert report.calendar_count == 1
    assert report.primary_calendar_count == 1
    assert report.cursor_was_reset is True
    assert report.fetched_count == 1
    assert report.created_count == 1
    assert report.provider_diagnostics == {
        "request_count": 5,
        "calendar_pages": 2,
        "event_pages": 2,
        "sync_token_resets": 1,
        "transport_errors": 0,
        "http_status_counts": {"200": 4, "410": 1},
    }
    serialized = json.dumps(report.as_dict())
    assert "private-access-token" not in serialized
    assert "private-account@example.test" not in serialized
    assert "private-calendar@example.test" not in serialized
    assert "private-new-cursor" not in serialized


def test_google_calendar_verification_returns_sanitized_failure_report() -> None:
    user, connection = create_connection("google-verification-failure")
    provider = GoogleCalendarProvider(
        "private-access-token",
        requester=ScriptedRequester(
            [response(429, {"error": {"message": "private-access-token"}})]
        ),
    )
    monotonic_values = iter([20.0, 20.01])

    report = GoogleCalendarVerificationService.verify(
        user=user,
        connection_id=connection.id,
        starts_at=START,
        starts_before=END,
        provider=provider,
        clock=FixedClock(END),
        monotonic=lambda: next(monotonic_values),
    )

    assert report.status == "fail"
    assert report.error_type == "ExternalCalendarRateLimitError"
    assert report.error == "Google Calendar rate limit exceeded"
    assert report.provider_diagnostics["http_status_counts"] == {"429": 1}
    connection.refresh_from_db()
    assert connection.status == "error"
    assert connection.last_error == "Google Calendar rate limit exceeded"
    assert "private-access-token" not in json.dumps(report.as_dict())


def test_verify_google_calendar_command_writes_sanitized_json(
    tmp_path: Path,
) -> None:
    user, connection = create_connection("google-verification-command")
    connection.sync_cursor = ""
    connection.save(update_fields=["sync_cursor", "updated_at"])
    provider = GoogleCalendarProvider(
        "private-access-token",
        requester=ScriptedRequester(
            [
                response(
                    200,
                    {
                        "items": [
                            {
                                "id": "private-calendar@example.test",
                                "summary": "Primary",
                                "timeZone": "Asia/Shanghai",
                                "primary": True,
                            }
                        ]
                    },
                ),
                response(200, {"items": [], "nextSyncToken": "private-cursor"}),
            ]
        ),
    )
    output_path = tmp_path / "google-calendar-report.json"
    stdout = StringIO()

    with patch(
        "apps.integrations.calendar.verification.build_calendar_provider",
        return_value=provider,
    ):
        call_command(
            "verify_google_calendar",
            "--user-id",
            str(user.pk),
            "--connection-id",
            str(connection.id),
            "--starts-at",
            "2026-08-24T00:00:00Z",
            "--starts-before",
            "2026-08-26T00:00:00Z",
            "--output",
            str(output_path),
            stdout=stdout,
        )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["database_vendor"] == database_connection.vendor
    assert payload["provider"]["request_count"] == 2
    assert "private-access-token" not in output_path.read_text(encoding="utf-8")
    assert "private-account@example.test" not in output_path.read_text(encoding="utf-8")
    assert "private-calendar@example.test" not in output_path.read_text(encoding="utf-8")
    assert output_path.stat().st_mode & 0o777 == 0o600
    assert "Wrote sanitized report" in stdout.getvalue()


def test_verify_google_calendar_command_checks_output_before_sync(
    tmp_path: Path,
) -> None:
    user, connection = create_connection("google-verification-existing-output")
    output_path = tmp_path / "existing-report.json"
    output_path.write_text("existing", encoding="utf-8")
    provider = GoogleCalendarProvider(
        "private-access-token",
        requester=ScriptedRequester([]),
    )

    with (
        patch(
            "apps.integrations.calendar.verification.build_calendar_provider",
            return_value=provider,
        ),
        pytest.raises(CommandError, match="already exists"),
    ):
        call_command(
            "verify_google_calendar",
            "--user-id",
            str(user.pk),
            "--connection-id",
            str(connection.id),
            "--starts-at",
            "2026-08-24T00:00:00Z",
            "--starts-before",
            "2026-08-26T00:00:00Z",
            "--output",
            str(output_path),
        )

    connection.refresh_from_db()
    assert connection.last_synced_at is None
    assert output_path.read_text(encoding="utf-8") == "existing"


def test_verify_google_calendar_command_writes_failure_report_and_exits_nonzero(
    tmp_path: Path,
) -> None:
    user, connection = create_connection("google-verification-command-failure")
    provider = GoogleCalendarProvider(
        "private-access-token",
        requester=ScriptedRequester(
            [response(429, {"error": {"message": "private-access-token"}})]
        ),
    )
    output_path = tmp_path / "failed-report.json"

    with (
        patch(
            "apps.integrations.calendar.verification.build_calendar_provider",
            return_value=provider,
        ),
        pytest.raises(CommandError, match="verification failed"),
    ):
        call_command(
            "verify_google_calendar",
            "--user-id",
            str(user.pk),
            "--connection-id",
            str(connection.id),
            "--starts-at",
            "2026-08-24T00:00:00Z",
            "--starts-before",
            "2026-08-26T00:00:00Z",
            "--output",
            str(output_path),
        )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert payload["error_type"] == "ExternalCalendarRateLimitError"
    assert payload["error"] == "Google Calendar rate limit exceeded"
    assert output_path.stat().st_mode & 0o777 == 0o600
    assert "private-access-token" not in output_path.read_text(encoding="utf-8")
