from datetime import UTC, datetime
from typing import assert_type

import pytest
from pydantic import ValidationError

from apps.integrations.calendar.capabilities import CalendarProviderCapabilities
from apps.integrations.calendar.contracts import ExternalCalendarProvider
from apps.integrations.calendar.dto import (
    ExternalCalendarContext,
    ExternalCalendarSummary,
    ExternalEvent,
    ExternalEventCreate,
    ExternalEventPage,
    ExternalEventQuery,
    ExternalEventUpdate,
)


class ContractProvider:
    provider_name = "contract-test"

    def get_capabilities(self) -> CalendarProviderCapabilities:
        return CalendarProviderCapabilities(read_calendars=True, read_events=True)

    def list_calendars(self, context: ExternalCalendarContext) -> list[ExternalCalendarSummary]:
        del context
        return []

    def list_events(
        self, context: ExternalCalendarContext, query: ExternalEventQuery
    ) -> ExternalEventPage:
        del context, query
        return ExternalEventPage(events=())

    def create_event(
        self, context: ExternalCalendarContext, event: ExternalEventCreate
    ) -> ExternalEvent:
        raise NotImplementedError

    def update_event(
        self, context: ExternalCalendarContext, external_event_id: str, event: ExternalEventUpdate
    ) -> ExternalEvent:
        raise NotImplementedError

    def cancel_event(self, context: ExternalCalendarContext, external_event_id: str) -> None:
        raise NotImplementedError


def test_provider_satisfies_protocol_and_dtos_are_json_serializable() -> None:
    provider: ExternalCalendarProvider = ContractProvider()
    assert_type(provider, ExternalCalendarProvider)
    context = ExternalCalendarContext(account_reference="opaque-account", timezone="Asia/Shanghai")
    query = ExternalEventQuery(
        calendar_id="primary",
        starts_at_or_after=datetime(2026, 7, 21, tzinfo=UTC),
        starts_before=datetime(2026, 7, 22, tzinfo=UTC),
    )
    assert provider.get_capabilities().read_events is True
    assert context.model_dump(mode="json")["timezone"] == "Asia/Shanghai"
    assert query.model_dump(mode="json")["starts_at_or_after"].endswith("Z")


def test_contract_rejects_naive_or_inverted_times() -> None:
    with pytest.raises(ValidationError):
        ExternalEventQuery(
            calendar_id="primary",
            starts_at_or_after=datetime(2026, 7, 21),
            starts_before=datetime(2026, 7, 22),
        )
    with pytest.raises(ValidationError):
        ExternalEventCreate(
            calendar_id="primary",
            title="Meeting",
            starts_at=datetime(2026, 7, 22, tzinfo=UTC),
            ends_at=datetime(2026, 7, 21, tzinfo=UTC),
            timezone="Asia/Shanghai",
        )
