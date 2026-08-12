from datetime import datetime
from typing import Literal
from uuid import UUID

from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, ConfigDict

from apps.agents.context import RuntimeContext
from apps.agents.tools.common import model_dict, require_actor, require_writable
from apps.conversations.services import AgentRunService
from apps.events.models import CalendarEventStatus
from apps.events.series_services import CreateEventSeriesCommand, EventSeriesService
from apps.events.services import CreateEventCommand, EventQuery, EventService, UpdateEventCommand
from apps.events.temporal_services import (
    EventTemporalResolutionService,
    EventTime,
    TemporalResolution,
)
from apps.tasks.services import TaskService

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
    "task_id",
    "version",
)


class EventDraftInput(BaseModel):
    """Schema for one finite batch member, parsed before the tool reaches services."""

    title: str
    start_at: datetime
    end_at: datetime
    timezone: str
    description: str = ""
    location: str = ""
    task_id: UUID | None = None


class EventMutationInput(BaseModel):
    """One member of an atomic calendar mutation request."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["create", "update", "cancel", "link_task"]
    event_id: UUID | None = None
    expected_version: int | None = None
    title: str | None = None
    time: EventTime | None = None
    description: str | None = None
    location: str | None = None
    task_id: UUID | None = None
def _record_temporal_resolution(
    runtime: ToolRuntime[RuntimeContext],
    resolution: TemporalResolution,
    *,
    target: str,
) -> None:
    if runtime.context.agent_run_id is None:
        return
    AgentRunService.record_temporal_resolution(
        run_id=UUID(runtime.context.agent_run_id),
        payload={"target": target, **resolution.as_audit_payload()},
    )


def _resolve_event_time(
    runtime: ToolRuntime[RuntimeContext],
    specification: EventTime,
    *,
    target: str,
) -> TemporalResolution:
    resolution = EventTemporalResolutionService.resolve(
        anchor_at=runtime.context.current_datetime,
        timezone=runtime.context.timezone,
        specification=specification,
    )
    _record_temporal_resolution(runtime, resolution, target=target)
    return resolution


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
def create_event(
    title: str,
    start_at: datetime,
    end_at: datetime,
    timezone: str,
    runtime: ToolRuntime[RuntimeContext],
    description: str = "",
    location: str = "",
    task_id: UUID | None = None,
) -> dict[str, object]:
    """Create a confirmed private event for the current user after checking its inputs."""

    actor = require_writable(runtime)
    task = TaskService.get_task(user=actor, task_id=task_id) if task_id else None
    event = EventService.create_event(
        CreateEventCommand(
            user=actor,
            task=task,
            created_by=actor,
            title=title,
            description=description,
            start_at=start_at,
            end_at=end_at,
            timezone=timezone,
            location=location,
            status=CalendarEventStatus.CONFIRMED,
            source="local",
            origin="agent",
        )
    )
    return model_dict(event, EVENT_FIELDS)


@tool
def update_event(
    event_id: UUID,
    expected_version: int,
    runtime: ToolRuntime[RuntimeContext],
    title: str | None = None,
    description: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    timezone: str | None = None,
    location: str | None = None,
) -> dict[str, object]:
    """Update one event. Time changes are conflict-checked by the service before saving."""

    changes = {
        key: value
        for key, value in {
            "title": title,
            "description": description,
            "start_at": start_at,
            "end_at": end_at,
            "timezone": timezone,
            "location": location,
        }.items()
        if value is not None
    }
    if not changes:
        raise ValueError("Provide at least one event field to update")
    event = EventService.update_event(
        UpdateEventCommand(
            user=require_writable(runtime),
            event_id=event_id,
            expected_version=expected_version,
            changes=changes,
            origin="agent",
            current_datetime=runtime.context.current_datetime,
        )
    )
    return model_dict(event, EVENT_FIELDS)


@tool
def set_event_task_link(
    event_id: UUID,
    expected_version: int,
    runtime: ToolRuntime[RuntimeContext],
    task_id: UUID | None = None,
) -> dict[str, object]:
    """Link an event to one of the user's tasks, or clear its task link."""

    actor = require_writable(runtime)
    task = TaskService.get_task(user=actor, task_id=task_id) if task_id else None
    event = EventService.update_event(
        UpdateEventCommand(
            user=actor,
            event_id=event_id,
            expected_version=expected_version,
            changes={"task": task},
            origin="agent",
            current_datetime=runtime.context.current_datetime,
        )
    )
    return model_dict(event, EVENT_FIELDS)


@tool
def create_event_batch(
    events: list[EventDraftInput],
    runtime: ToolRuntime[RuntimeContext],
) -> list[dict[str, object]]:
    """Create a finite group of events atomically; every time range is conflict-checked."""

    actor = require_writable(runtime)
    commands: list[CreateEventCommand] = []
    for item in events:
        task = TaskService.get_task(user=actor, task_id=item.task_id) if item.task_id else None
        commands.append(
            CreateEventCommand(
                user=actor,
                created_by=actor,
                title=item.title,
                start_at=item.start_at,
                end_at=item.end_at,
                timezone=item.timezone,
                description=item.description,
                location=item.location,
                task=task,
                status=CalendarEventStatus.CONFIRMED,
                source="local",
                origin="agent",
            )
        )
    created = EventService.create_events(commands=commands)
    return [model_dict(event, EVENT_FIELDS) for event in created]


@tool
def mutate_events(
    operations: list[EventMutationInput],
    runtime: ToolRuntime[RuntimeContext],
) -> list[dict[str, object]]:
    """Atomically create, update, cancel, or link one or many calendar events after one approval."""

    actor = require_writable(runtime)
    if not operations:
        raise ValueError("Provide at least one event operation")
    results: list[dict[str, object]] = []
    for operation_index, operation in enumerate(operations):
        if operation.action == "create":
            if operation.title is None or operation.time is None:
                raise ValueError("Create requires title and time")
            resolution = _resolve_event_time(
                runtime,
                operation.time,
                target=f"mutate_events.operations[{operation_index}].time",
            )
            task = (
                TaskService.get_task(user=actor, task_id=operation.task_id)
                if operation.task_id
                else None
            )
            event = EventService.create_event(
                CreateEventCommand(
                    user=actor,
                    created_by=actor,
                    task=task,
                    title=operation.title,
                    start_at=resolution.start_at,
                    end_at=resolution.end_at,
                    timezone=runtime.context.timezone,
                    description=operation.description or "",
                    location=operation.location or "",
                    origin="agent",
                )
            )
        elif operation.action == "update":
            if operation.event_id is None or operation.expected_version is None:
                raise ValueError("Update requires event_id and expected_version")
            update_resolution = (
                _resolve_event_time(
                    runtime,
                    operation.time,
                    target=f"mutate_events.operations[{operation_index}].time",
                )
                if operation.time is not None
                else None
            )
            changes = {
                key: value
                for key, value in {
                    "title": operation.title,
                    "start_at": update_resolution.start_at if update_resolution else None,
                    "end_at": update_resolution.end_at if update_resolution else None,
                    "timezone": runtime.context.timezone if update_resolution else None,
                    "description": operation.description,
                    "location": operation.location,
                }.items()
                if value is not None
            }
            if not changes:
                raise ValueError("Update requires at least one changed event field")
            event = EventService.update_event(
                UpdateEventCommand(
                    user=actor,
                    event_id=operation.event_id,
                    expected_version=operation.expected_version,
                    changes=changes,
                    origin="agent",
                    current_datetime=runtime.context.current_datetime,
                )
            )
        elif operation.action == "cancel":
            if operation.event_id is None or operation.expected_version is None:
                raise ValueError("Cancel requires event_id and expected_version")
            event = EventService.cancel_event(
                event_id=operation.event_id,
                user=actor,
                expected_version=operation.expected_version,
                origin="agent",
                current_datetime=runtime.context.current_datetime,
            )
        elif operation.action == "link_task":
            if operation.event_id is None or operation.expected_version is None:
                raise ValueError("link_task requires event_id and expected_version")
            task = (
                TaskService.get_task(user=actor, task_id=operation.task_id)
                if operation.task_id
                else None
            )
            event = EventService.update_event(
                UpdateEventCommand(
                    user=actor,
                    event_id=operation.event_id,
                    expected_version=operation.expected_version,
                    changes={"task": task},
                    origin="agent",
                    current_datetime=runtime.context.current_datetime,
                )
            )
        else:
            raise ValueError("Unsupported event action")
        results.append(model_dict(event, EVENT_FIELDS))
    return results


@tool
def create_recurring_event(
    title: str,
    time: EventTime,
    frequency: str,
    occurrence_count: int,
    runtime: ToolRuntime[RuntimeContext],
    interval: int = 1,
    description: str = "",
    location: str = "",
    task_id: UUID | None = None,
) -> dict[str, object]:
    """Create a finite event series using an explicit absolute or relative time variant."""

    actor = require_writable(runtime)
    resolution = _resolve_event_time(
        runtime,
        time,
        target="create_recurring_event.time",
    )
    task = TaskService.get_task(user=actor, task_id=task_id) if task_id else None
    series = EventSeriesService.create_series(
        CreateEventSeriesCommand(
            user=actor,
            task=task,
            title=title,
            description=description,
            start_at=resolution.start_at,
            end_at=resolution.end_at,
            timezone=runtime.context.timezone,
            location=location,
            frequency=frequency,
            interval=interval,
            occurrence_count=occurrence_count,
            origin="agent",
        )
    )
    return {"series_id": str(series.pk), "occurrence_count": series.occurrences.count()}


@tool
def cancel_event(
    event_id: UUID,
    expected_version: int,
    runtime: ToolRuntime[RuntimeContext],
) -> dict[str, object]:
    """Cancel one identified event; first read it and pass its current version."""

    event = EventService.cancel_event(
        event_id=event_id,
        user=require_writable(runtime),
        expected_version=expected_version,
        origin="agent",
        current_datetime=runtime.context.current_datetime,
    )
    return model_dict(event, EVENT_FIELDS)


EVENT_READ_TOOLS = [list_events, get_event]
EVENT_WRITE_TOOLS = [
    mutate_events,
    create_recurring_event,
]
EVENT_TOOLS = [*EVENT_READ_TOOLS, *EVENT_WRITE_TOOLS]
