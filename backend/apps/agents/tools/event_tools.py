from datetime import datetime
from uuid import UUID

from langchain.tools import ToolRuntime, tool

from apps.agents.context import RuntimeContext
from apps.agents.tools.common import model_dict, require_actor, require_writable
from apps.events.models import CalendarEventStatus
from apps.events.services import CreateEventCommand, EventQuery, EventService

EVENT_FIELDS = (
    "id",
    "title",
    "description",
    "start_at",
    "end_at",
    "timezone",
    "location",
    "status",
    "visibility",
    "version",
)


@tool
def list_events(
    starts_before: datetime | None = None,
    ends_after: datetime | None = None,
    statuses: list[str] | None = None,
    runtime: ToolRuntime[RuntimeContext] = None,  # type: ignore[assignment]
) -> list[dict[str, object]]:
    """List the current user's calendar events in an optional UTC-aware time range."""

    actor = require_actor(runtime)
    events = EventService.list_events(
        EventQuery(
            user=actor,
            starts_before=starts_before,
            ends_after=ends_after,
            statuses=tuple(statuses or ()),
        )
    )
    return [model_dict(event, EVENT_FIELDS) for event in events]


@tool
def get_event(event_id: UUID, runtime: ToolRuntime[RuntimeContext]) -> dict[str, object]:
    """Get one calendar event owned by the current user."""

    event = EventService.get_event(user=require_actor(runtime), event_id=event_id)
    return model_dict(event, EVENT_FIELDS)


@tool
def detect_conflicts(
    start_at: datetime,
    end_at: datetime,
    runtime: ToolRuntime[RuntimeContext],
    exclude_event_id: UUID | None = None,
) -> list[dict[str, object]]:
    """Find calendar events that overlap a proposed UTC-aware time range."""

    events = EventService.detect_conflicts(
        user=require_actor(runtime),
        start_at=start_at,
        end_at=end_at,
        exclude_event_id=exclude_event_id,
    )
    return [model_dict(event, EVENT_FIELDS) for event in events]


@tool
def create_event(
    title: str,
    start_at: datetime,
    end_at: datetime,
    timezone: str,
    runtime: ToolRuntime[RuntimeContext],
    description: str = "",
    location: str = "",
) -> dict[str, object]:
    """Create a confirmed private event for the current user after checking its inputs."""

    actor = require_writable(runtime)
    event = EventService.create_event(
        CreateEventCommand(
            user=actor,
            created_by=actor,
            title=title,
            description=description,
            start_at=start_at,
            end_at=end_at,
            timezone=timezone,
            location=location,
            status=CalendarEventStatus.CONFIRMED,
            source="local",
        )
    )
    return model_dict(event, EVENT_FIELDS)


EVENT_TOOLS = [list_events, get_event, detect_conflicts, create_event]
