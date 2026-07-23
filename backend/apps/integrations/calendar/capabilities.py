from pydantic import BaseModel, ConfigDict


class CalendarProviderCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    read_calendars: bool = False
    read_events: bool = False
    create_events: bool = False
    update_events: bool = False
    cancel_events: bool = False
    incremental_sync: bool = False
    webhooks: bool = False
    recurrence: bool = False
    attendees: bool = False
