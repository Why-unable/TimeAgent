from datetime import UTC, datetime

import httpx
import pytest

from apps.integrations.calendar.dto import (
    ExternalCalendarContext,
    ExternalEvent,
    ExternalEventQuery,
)
from apps.integrations.calendar.exceptions import (
    ExternalCalendarAuthenticationError,
    ExternalCalendarPermanentError,
)
from apps.integrations.calendar.providers.ics import IcsCalendarProvider

ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-1@example.com
DTSTART:20260824T090000Z
DTEND:20260824T100000Z
SUMMARY:Planning review
DESCRIPTION:Review the draft
END:VEVENT
END:VCALENDAR
"""


def test_ics_provider_reads_events_without_write_capabilities() -> None:
    provider = IcsCalendarProvider(fetcher=lambda _url: ICS)
    context = ExternalCalendarContext(
        account_reference="https://calendar.example/feed.ics", timezone="Asia/Shanghai"
    )
    page = provider.list_events(
        context,
        ExternalEventQuery(
            calendar_id=context.account_reference,
            starts_at_or_after=datetime(2026, 8, 24, 0, tzinfo=UTC),
            starts_before=datetime(2026, 8, 25, 0, tzinfo=UTC),
        ),
    )
    assert provider.get_capabilities().create_events is False
    assert len(page.events) == 1
    event = page.events[0]
    assert isinstance(event, ExternalEvent)
    assert event.title == "Planning review"
    assert event.starts_at == datetime(2026, 8, 24, 9, tzinfo=UTC)


def test_ics_provider_redacts_private_feed_url_from_http_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_url = "https://8.8.8.8/feed.ics?token=private-secret"

    def unauthorized(url: str, **kwargs: object) -> httpx.Response:
        del kwargs
        return httpx.Response(401, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", unauthorized)
    provider = IcsCalendarProvider()

    with pytest.raises(
        ExternalCalendarAuthenticationError,
        match="Calendar provider authentication failed",
    ) as error:
        provider.list_events(
            ExternalCalendarContext(account_reference=private_url, timezone="Asia/Shanghai"),
            ExternalEventQuery(
                calendar_id=private_url,
                starts_at_or_after=datetime(2026, 8, 24, 0, tzinfo=UTC),
                starts_before=datetime(2026, 8, 25, 0, tzinfo=UTC),
            ),
        )

    assert "private-secret" not in str(error.value)


def test_ics_provider_rejects_private_network_targets() -> None:
    with pytest.raises(ExternalCalendarPermanentError, match="host is not allowed"):
        IcsCalendarProvider._fetch("http://127.0.0.1:8000/private.ics")
