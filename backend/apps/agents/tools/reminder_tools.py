from datetime import datetime
from uuid import UUID

from langchain.tools import ToolRuntime, tool

from apps.agents.context import RuntimeContext
from apps.agents.tools.common import (
    model_dict,
    require_actor,
    require_writable,
    tool_idempotency_key,
)
from apps.reminders.models import ReminderTargetType
from apps.reminders.services import (
    CreateReminderCommand,
    ReminderQuery,
    ReminderService,
    UpdateReminderCommand,
)

REMINDER_FIELDS = (
    "id",
    "title",
    "trigger_at",
    "timezone",
    "channel",
    "target_type",
    "target_id",
    "status",
    "failure_reason",
    "retry_count",
    "version",
)


@tool
def list_reminders(
    statuses: list[str] | None = None,
    trigger_before: datetime | None = None,
    runtime: ToolRuntime[RuntimeContext] = None,  # type: ignore[assignment]
) -> list[dict[str, object]]:
    """List reminders owned by the current user with optional filters."""

    reminders = ReminderService.list_reminders(
        ReminderQuery(
            user=require_actor(runtime),
            statuses=tuple(statuses or ()),
            trigger_before=trigger_before,
        )
    )
    return [model_dict(reminder, REMINDER_FIELDS) for reminder in reminders]


@tool
def get_reminder(
    reminder_id: UUID,
    runtime: ToolRuntime[RuntimeContext],
) -> dict[str, object]:
    """Get one reminder owned by the current user."""

    reminder = ReminderService.get_reminder(
        user=require_actor(runtime),
        reminder_id=reminder_id,
    )
    return model_dict(reminder, REMINDER_FIELDS)


@tool
def create_reminder(
    title: str,
    trigger_at: datetime,
    timezone: str,
    runtime: ToolRuntime[RuntimeContext],
    target_type: str = ReminderTargetType.CUSTOM,
    target_id: UUID | None = None,
) -> dict[str, object]:
    """Create an idempotent reminder, optionally bound to one of the user's tasks or events."""

    reminder = ReminderService.create_reminder(
        CreateReminderCommand(
            user=require_writable(runtime),
            title=title,
            trigger_at=trigger_at,
            timezone=timezone,
            deduplication_key=tool_idempotency_key(runtime, purpose="create-reminder"),
            target_type=target_type,
            target_id=target_id,
        )
    )
    return model_dict(reminder, REMINDER_FIELDS)


@tool
def update_reminder(
    reminder_id: UUID,
    expected_version: int,
    runtime: ToolRuntime[RuntimeContext],
    title: str | None = None,
    trigger_at: datetime | None = None,
    timezone: str | None = None,
    channel: str | None = None,
) -> dict[str, object]:
    """Edit a pending reminder's content, delivery time, timezone, or channel."""

    changes = {
        key: value
        for key, value in {
            "title": title,
            "trigger_at": trigger_at,
            "timezone": timezone,
            "channel": channel,
        }.items()
        if value is not None
    }
    if not changes:
        raise ValueError("Provide at least one reminder field to update")
    reminder = ReminderService.update_reminder(
        UpdateReminderCommand(
            user=require_writable(runtime),
            reminder_id=reminder_id,
            expected_version=expected_version,
            changes=changes,
        )
    )
    return model_dict(reminder, REMINDER_FIELDS)


@tool
def set_reminder_target(
    reminder_id: UUID,
    expected_version: int,
    target_type: str,
    runtime: ToolRuntime[RuntimeContext],
    target_id: UUID | None = None,
) -> dict[str, object]:
    """Bind an editable reminder to an event/task or make it an independent reminder."""

    reminder = ReminderService.update_reminder(
        UpdateReminderCommand(
            user=require_writable(runtime),
            reminder_id=reminder_id,
            expected_version=expected_version,
            changes={"target_type": target_type, "target_id": target_id},
        )
    )
    return model_dict(reminder, REMINDER_FIELDS)


@tool
def cancel_reminder(
    reminder_id: UUID,
    runtime: ToolRuntime[RuntimeContext],
) -> dict[str, object]:
    """Cancel one identified reminder if it has not started or been sent."""

    reminder = ReminderService.cancel_reminder(
        reminder_id=reminder_id,
        user=require_writable(runtime),
        occurred_at=runtime.context.current_datetime,
    )
    return model_dict(reminder, REMINDER_FIELDS)


REMINDER_READ_TOOLS = [list_reminders, get_reminder]
REMINDER_WRITE_TOOLS = [
    create_reminder,
    update_reminder,
    set_reminder_target,
    cancel_reminder,
]
REMINDER_TOOLS = [*REMINDER_READ_TOOLS, *REMINDER_WRITE_TOOLS]
