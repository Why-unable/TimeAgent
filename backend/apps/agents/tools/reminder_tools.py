from datetime import datetime
from uuid import UUID

from langchain.tools import ToolRuntime, tool

from apps.agents.context import RuntimeContext
from apps.agents.tools.common import model_dict, require_actor, require_writable
from apps.reminders.services import CreateReminderCommand, ReminderQuery, ReminderService

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
    idempotency_key: str,
    runtime: ToolRuntime[RuntimeContext],
) -> dict[str, object]:
    """Create an idempotent console reminder for the current user."""

    reminder = ReminderService.create_reminder(
        CreateReminderCommand(
            user=require_writable(runtime),
            title=title,
            trigger_at=trigger_at,
            timezone=timezone,
            deduplication_key=idempotency_key,
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


REMINDER_TOOLS = [list_reminders, get_reminder, create_reminder, cancel_reminder]
