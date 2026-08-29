from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from urllib.parse import quote

import httpx

from apps.integrations.calendar.capabilities import CalendarProviderCapabilities
from apps.integrations.calendar.dto import (
    ExternalCalendarContext,
    ExternalCalendarSummary,
    ExternalEvent,
    ExternalEventPage,
    ExternalEventQuery,
    ExternalEventTombstone,
)
from apps.integrations.calendar.exceptions import (
    ExternalCalendarAuthenticationError,
    ExternalCalendarPermanentError,
    ExternalCalendarRateLimitError,
    ExternalCalendarTemporaryError,
)
from common.time import get_timezone

GoogleRequest = Callable[..., httpx.Response]


@dataclass(frozen=True, slots=True)
class GoogleCalendarDiagnostics:
    request_count: int
    calendar_pages: int
    event_pages: int
    sync_token_resets: int
    transport_errors: int
    http_status_counts: tuple[tuple[int, int], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "request_count": self.request_count,
            "calendar_pages": self.calendar_pages,
            "event_pages": self.event_pages,
            "sync_token_resets": self.sync_token_resets,
            "transport_errors": self.transport_errors,
            "http_status_counts": {
                str(status_code): count
                for status_code, count in self.http_status_counts
            },
        }


class GoogleCalendarProvider:
    provider_name = "google"
    api_base_url = "https://www.googleapis.com/calendar/v3"
    max_pages = 100

    def __init__(
        self,
        access_token: str,
        *,
        requester: GoogleRequest | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        token = access_token.strip()
        if not token:
            raise ExternalCalendarAuthenticationError("Google access token is unavailable")
        self._access_token = token
        self._requester = requester or httpx.request
        self._timeout_seconds = timeout_seconds
        self._request_count = 0
        self._calendar_pages = 0
        self._event_pages = 0
        self._sync_token_resets = 0
        self._transport_errors = 0
        self._http_status_counts: dict[int, int] = {}

    def diagnostics(self) -> GoogleCalendarDiagnostics:
        return GoogleCalendarDiagnostics(
            request_count=self._request_count,
            calendar_pages=self._calendar_pages,
            event_pages=self._event_pages,
            sync_token_resets=self._sync_token_resets,
            transport_errors=self._transport_errors,
            http_status_counts=tuple(sorted(self._http_status_counts.items())),
        )

    def get_capabilities(self) -> CalendarProviderCapabilities:
        return CalendarProviderCapabilities(
            read_calendars=True,
            read_events=True,
            incremental_sync=True,
            recurrence=True,
        )

    def list_calendars(self, context: ExternalCalendarContext) -> list[ExternalCalendarSummary]:
        calendars: list[ExternalCalendarSummary] = []
        page_token = ""
        seen_tokens: set[str] = set()
        for _ in range(self.max_pages):
            params = {"maxResults": "250"}
            if page_token:
                params["pageToken"] = page_token
            payload = self._request_json(
                "GET",
                f"{self.api_base_url}/users/me/calendarList",
                params=params,
            )
            self._calendar_pages += 1
            for item in self._items(payload):
                calendar_id = self._required_text(item, "id")
                timezone_name = self._optional_text(item, "timeZone") or context.timezone
                try:
                    calendars.append(
                        ExternalCalendarSummary(
                            external_id=calendar_id,
                            name=self._optional_text(item, "summary") or calendar_id,
                            timezone=timezone_name,
                            is_primary=bool(item.get("primary", False)),
                            read_only=True,
                        )
                    )
                except ValueError as exc:
                    raise ExternalCalendarTemporaryError(
                        "Google Calendar returned invalid calendar data"
                    ) from exc
            page_token = self._optional_text(payload, "nextPageToken")
            if not page_token:
                return calendars
            if page_token in seen_tokens:
                raise ExternalCalendarTemporaryError("Google Calendar pagination repeated a token")
            seen_tokens.add(page_token)
        raise ExternalCalendarTemporaryError("Google Calendar pagination limit exceeded")

    def list_events(
        self,
        context: ExternalCalendarContext,
        query: ExternalEventQuery,
    ) -> ExternalEventPage:
        try:
            return self._list_event_pages(context, query, sync_cursor=query.sync_cursor)
        except _GoogleSyncTokenExpired as exc:
            if not query.sync_cursor:
                raise ExternalCalendarPermanentError(
                    "Google Calendar rejected the sync request"
                ) from exc
            self._sync_token_resets += 1
            page = self._list_event_pages(context, query, sync_cursor="")
            return page.model_copy(update={"cursor_was_reset": True})

    def _list_event_pages(
        self,
        context: ExternalCalendarContext,
        query: ExternalEventQuery,
        *,
        sync_cursor: str,
    ) -> ExternalEventPage:
        events: list[ExternalEvent | ExternalEventTombstone] = []
        page_token = ""
        seen_tokens: set[str] = set()
        next_sync_cursor = ""
        url = f"{self.api_base_url}/calendars/{quote(query.calendar_id, safe='')}/events"
        for _ in range(self.max_pages):
            params = self._event_params(query, sync_cursor=sync_cursor, page_token=page_token)
            response = self._request("GET", url, params=params, allow_sync_token_expiry=True)
            self._event_pages += 1
            payload = self._json_object(response)
            for item in self._items(payload):
                try:
                    parsed = self._parse_event(
                        item,
                        context=context,
                        calendar_id=query.calendar_id,
                    )
                except ValueError as exc:
                    raise ExternalCalendarTemporaryError(
                        "Google Calendar returned invalid event data"
                    ) from exc
                if parsed is not None:
                    events.append(parsed)
            page_token = self._optional_text(payload, "nextPageToken")
            if not page_token:
                next_sync_cursor = self._optional_text(payload, "nextSyncToken")
                if not next_sync_cursor:
                    raise ExternalCalendarTemporaryError(
                        "Google Calendar did not return a sync token"
                    )
                return ExternalEventPage(
                    events=tuple(events),
                    next_sync_cursor=next_sync_cursor,
                )
            if page_token in seen_tokens:
                raise ExternalCalendarTemporaryError("Google Calendar pagination repeated a token")
            seen_tokens.add(page_token)
        raise ExternalCalendarTemporaryError("Google Calendar pagination limit exceeded")

    @staticmethod
    def _event_params(
        query: ExternalEventQuery,
        *,
        sync_cursor: str,
        page_token: str,
    ) -> dict[str, str]:
        params = {
            "maxResults": "2500",
            "showDeleted": "true",
            "singleEvents": "true",
        }
        if sync_cursor:
            params["syncToken"] = sync_cursor
        else:
            params["timeMin"] = query.starts_at_or_after.astimezone(UTC).isoformat().replace(
                "+00:00", "Z"
            )
            params["timeMax"] = query.starts_before.astimezone(UTC).isoformat().replace(
                "+00:00", "Z"
            )
        if page_token:
            params["pageToken"] = page_token
        return params

    def _parse_event(
        self,
        item: Mapping[str, Any],
        *,
        context: ExternalCalendarContext,
        calendar_id: str,
    ) -> ExternalEvent | ExternalEventTombstone | None:
        external_id = self._optional_text(item, "id")
        if not external_id:
            return None
        status = self._optional_text(item, "status") or "confirmed"
        if status == "cancelled":
            return ExternalEventTombstone(external_id=external_id, calendar_id=calendar_id)
        start = item.get("start")
        end = item.get("end")
        if not isinstance(start, Mapping) or not isinstance(end, Mapping):
            return None
        timezone_name = (
            self._optional_text(start, "timeZone")
            or self._optional_text(end, "timeZone")
            or context.timezone
        )
        starts_at = self._parse_event_time(start, timezone_name)
        ends_at = self._parse_event_time(end, timezone_name)
        if starts_at is None or ends_at is None or starts_at >= ends_at:
            return None
        return ExternalEvent(
            external_id=external_id,
            calendar_id=calendar_id,
            title=self._optional_text(item, "summary") or "(无标题)",
            starts_at=starts_at,
            ends_at=ends_at,
            timezone=timezone_name,
            description=self._optional_text(item, "description"),
            location=self._optional_text(item, "location"),
            status=status,
            etag=self._optional_text(item, "etag"),
        )

    @staticmethod
    def _parse_event_time(value: Mapping[str, Any], timezone_name: str) -> datetime | None:
        date_time = GoogleCalendarProvider._optional_text(value, "dateTime")
        if date_time:
            parsed = datetime.fromisoformat(date_time.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=get_timezone(timezone_name))
            return parsed.astimezone(UTC)
        date_text = GoogleCalendarProvider._optional_text(value, "date")
        if date_text:
            local_date = date.fromisoformat(date_text)
            local_midnight = datetime.combine(
                local_date,
                time.min,
                tzinfo=get_timezone(timezone_name),
            )
            return local_midnight.astimezone(UTC)
        return None

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str],
    ) -> dict[str, Any]:
        return self._json_object(self._request(method, url, params=params))

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str],
        allow_sync_token_expiry: bool = False,
    ) -> httpx.Response:
        self._request_count += 1
        try:
            response = self._requester(
                method,
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self._access_token}",
                },
                params=params,
                timeout=self._timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            self._transport_errors += 1
            raise ExternalCalendarTemporaryError("Google Calendar request timed out") from exc
        except httpx.RequestError as exc:
            self._transport_errors += 1
            raise ExternalCalendarTemporaryError("Google Calendar is unavailable") from exc
        self._http_status_counts[response.status_code] = (
            self._http_status_counts.get(response.status_code, 0) + 1
        )
        if response.status_code == 410 and allow_sync_token_expiry:
            raise _GoogleSyncTokenExpired
        if response.status_code in {401, 403}:
            raise ExternalCalendarAuthenticationError("Google Calendar authorization failed")
        if response.status_code == 429:
            raise ExternalCalendarRateLimitError("Google Calendar rate limit exceeded")
        if response.status_code >= 500:
            raise ExternalCalendarTemporaryError("Google Calendar is temporarily unavailable")
        if response.is_error:
            raise ExternalCalendarPermanentError("Google Calendar rejected the request")
        return response

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ExternalCalendarTemporaryError(
                "Google Calendar returned malformed JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise ExternalCalendarTemporaryError("Google Calendar returned malformed JSON")
        return payload

    @staticmethod
    def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise ExternalCalendarTemporaryError("Google Calendar returned malformed items")
        return [item for item in items if isinstance(item, Mapping)]

    @staticmethod
    def _required_text(payload: Mapping[str, Any], key: str) -> str:
        value = GoogleCalendarProvider._optional_text(payload, key)
        if not value:
            raise ExternalCalendarTemporaryError(f"Google Calendar item is missing {key}")
        return value

    @staticmethod
    def _optional_text(payload: Mapping[str, Any], key: str) -> str:
        value = payload.get(key)
        return value.strip() if isinstance(value, str) else ""

    def create_event(self, *args: Any, **kwargs: Any) -> ExternalEvent:
        raise NotImplementedError("Google Calendar integration is read-only")

    def update_event(self, *args: Any, **kwargs: Any) -> ExternalEvent:
        raise NotImplementedError("Google Calendar integration is read-only")

    def cancel_event(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError("Google Calendar integration is read-only")


class _GoogleSyncTokenExpired(Exception):
    pass
