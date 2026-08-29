from __future__ import annotations

import socket
from collections.abc import Callable
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

from apps.integrations.calendar.capabilities import CalendarProviderCapabilities
from apps.integrations.calendar.dto import (
    ExternalCalendarContext,
    ExternalCalendarSummary,
    ExternalEvent,
    ExternalEventPage,
    ExternalEventQuery,
)
from apps.integrations.calendar.exceptions import (
    ExternalCalendarAuthenticationError,
    ExternalCalendarPermanentError,
    ExternalCalendarRateLimitError,
    ExternalCalendarTemporaryError,
)


class IcsCalendarProvider:
    """Read-only HTTP ICS adapter; account_reference is the configured feed URL."""

    provider_name = "ics"

    def __init__(self, fetcher: Callable[[str], str] | None = None) -> None:
        self._fetcher = fetcher or self._fetch

    def get_capabilities(self) -> CalendarProviderCapabilities:
        return CalendarProviderCapabilities(read_calendars=True, read_events=True)

    def list_calendars(self, context: ExternalCalendarContext) -> list[ExternalCalendarSummary]:
        return [
            ExternalCalendarSummary(
                external_id=context.account_reference,
                name="ICS feed",
                timezone=context.timezone,
                is_primary=True,
                read_only=True,
            )
        ]

    def list_events(
        self, context: ExternalCalendarContext, query: ExternalEventQuery
    ) -> ExternalEventPage:
        if query.calendar_id != context.account_reference:
            return ExternalEventPage(events=())
        events = tuple(
            event
            for event in self._parse(self._fetcher(context.account_reference), context, query)
            if event.ends_at > query.starts_at_or_after and event.starts_at < query.starts_before
        )
        return ExternalEventPage(events=events)

    def create_event(self, *args: Any, **kwargs: Any) -> ExternalEvent:
        raise NotImplementedError("ICS feeds are read-only")

    def update_event(self, *args: Any, **kwargs: Any) -> ExternalEvent:
        raise NotImplementedError("ICS feeds are read-only")

    def cancel_event(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError("ICS feeds are read-only")

    @staticmethod
    def _fetch(url: str) -> str:
        IcsCalendarProvider._assert_safe_url(url)
        try:
            response = httpx.get(url, timeout=10.0, follow_redirects=False)
        except httpx.TimeoutException as exc:
            raise ExternalCalendarTemporaryError("Calendar provider timed out") from exc
        except httpx.RequestError as exc:
            raise ExternalCalendarTemporaryError("Calendar provider is unavailable") from exc
        if response.status_code in {401, 403}:
            raise ExternalCalendarAuthenticationError("Calendar provider authentication failed")
        if response.status_code == 429:
            raise ExternalCalendarRateLimitError("Calendar provider rate limit exceeded")
        if response.status_code >= 500:
            raise ExternalCalendarTemporaryError("Calendar provider is temporarily unavailable")
        if response.is_error or response.is_redirect:
            raise ExternalCalendarPermanentError("Calendar provider rejected the request")
        return response.text

    @staticmethod
    def _assert_safe_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
            raise ExternalCalendarPermanentError(
                "ICS feed URL must be an absolute HTTP(S) URL"
            )
        if parsed.username or parsed.password:
            raise ExternalCalendarPermanentError(
                "Calendar feed credentials in URLs are not allowed"
            )
        hostname = parsed.hostname.lower().rstrip(".")
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise ExternalCalendarPermanentError("Calendar feed host is not allowed")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except (OSError, ValueError) as exc:
            raise ExternalCalendarTemporaryError(
                "Calendar feed host could not be resolved"
            ) from exc
        if not addresses:
            raise ExternalCalendarTemporaryError("Calendar feed host could not be resolved")
        for address in addresses:
            resolved = ip_address(address[4][0])
            if not resolved.is_global:
                raise ExternalCalendarPermanentError("Calendar feed host is not allowed")

    @staticmethod
    def _parse(
        content: str,
        context: ExternalCalendarContext,
        query: ExternalEventQuery,
    ) -> list[ExternalEvent]:
        lines: list[str] = []
        for line in content.replace("\r\n", "\n").split("\n"):
            if line.startswith((" ", "\t")) and lines:
                lines[-1] += line[1:]
            else:
                lines.append(line)
        events: list[ExternalEvent] = []
        current: dict[str, str] | None = None
        for line in lines:
            if line == "BEGIN:VEVENT":
                current = {}
            elif line == "END:VEVENT" and current is not None:
                event = IcsCalendarProvider._event_from_fields(current, context, query)
                if event is not None:
                    events.append(event)
                current = None
            elif current is not None and ":" in line:
                key, value = line.split(":", 1)
                current[key.split(";", 1)[0].upper()] = value.strip()
        return events

    @staticmethod
    def _event_from_fields(
        fields: dict[str, str], context: ExternalCalendarContext, query: ExternalEventQuery
    ) -> ExternalEvent | None:
        uid = fields.get("UID")
        title = fields.get("SUMMARY")
        start_value = fields.get("DTSTART")
        end_value = fields.get("DTEND")
        if not uid or not title or not start_value or not end_value:
            return None
        starts_at = IcsCalendarProvider._parse_datetime(start_value, context.timezone)
        ends_at = IcsCalendarProvider._parse_datetime(end_value, context.timezone)
        if starts_at >= ends_at:
            return None
        return ExternalEvent(
            external_id=uid,
            calendar_id=context.account_reference,
            title=title,
            starts_at=starts_at,
            ends_at=ends_at,
            timezone=context.timezone,
            description=fields.get("DESCRIPTION", ""),
            location=fields.get("LOCATION", ""),
            status=fields.get("STATUS", "confirmed").lower(),
            etag=fields.get("LAST-MODIFIED", ""),
        )

    @staticmethod
    def _parse_datetime(value: str, timezone_name: str) -> datetime:
        if len(value) == 8 and value.isdigit():
            local = datetime.strptime(value, "%Y%m%d").replace(tzinfo=ZoneInfo(timezone_name))
            return local.astimezone(UTC)
        normalized = value.rstrip("Z")
        parsed = datetime.strptime(normalized, "%Y%m%dT%H%M%S")
        if value.endswith("Z"):
            return parsed.replace(tzinfo=UTC)
        return parsed.replace(tzinfo=ZoneInfo(timezone_name)).astimezone(UTC)
