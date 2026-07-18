from datetime import datetime

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


REMINDER_TOOLS = [list_reminders, create_reminder]
