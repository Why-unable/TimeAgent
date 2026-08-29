from apps.integrations.calendar.contracts import ExternalCalendarProvider
from apps.integrations.calendar.oauth_services import CalendarCredentialService
from apps.integrations.calendar.providers.google import GoogleCalendarProvider
from apps.integrations.calendar.providers.ics import IcsCalendarProvider
from apps.integrations.models import CalendarSyncConnection


def build_calendar_provider(connection: CalendarSyncConnection) -> ExternalCalendarProvider:
    if connection.provider_name == "ics":
        return IcsCalendarProvider()
    if connection.provider_name == "google":
        return GoogleCalendarProvider(
            CalendarCredentialService.access_token_for_connection(connection=connection)
        )
    raise ValueError(f"Unsupported calendar provider: {connection.provider_name}")
