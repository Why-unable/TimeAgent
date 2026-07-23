from typing import Protocol

from apps.integrations.calendar.capabilities import CalendarProviderCapabilities
from apps.integrations.calendar.dto import (
    ExternalCalendarContext,
    ExternalCalendarSummary,
    ExternalEvent,
    ExternalEventCreate,
    ExternalEventQuery,
    ExternalEventUpdate,
)


class ExternalCalendarProvider(Protocol):
    provider_name: str

    def get_capabilities(self) -> CalendarProviderCapabilities: ...

    def list_calendars(self, context: ExternalCalendarContext) -> list[ExternalCalendarSummary]: ...

    def list_events(
        self, context: ExternalCalendarContext, query: ExternalEventQuery
    ) -> list[ExternalEvent]: ...

    def create_event(
        self, context: ExternalCalendarContext, event: ExternalEventCreate
    ) -> ExternalEvent: ...

    def update_event(
        self, context: ExternalCalendarContext, external_event_id: str, event: ExternalEventUpdate
    ) -> ExternalEvent: ...

    def cancel_event(self, context: ExternalCalendarContext, external_event_id: str) -> None: ...
