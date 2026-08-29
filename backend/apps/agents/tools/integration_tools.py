from langchain.tools import ToolRuntime, tool

from apps.agents.context import RuntimeContext
from apps.agents.tools.common import require_actor
from apps.integrations.calendar.sync_services import CalendarSyncService


@tool
def list_calendar_sync_status(
    runtime: ToolRuntime[RuntimeContext],
) -> list[dict[str, object]]:
    """List the user's read-only external calendar connection status without credentials."""

    connections = CalendarSyncService.list_connections(user=require_actor(runtime))
    return [
        {
            "connection_id": str(connection.pk),
            "provider_name": connection.provider_name,
            "calendar_name": connection.calendar_name,
            "timezone": connection.timezone,
            "enabled": connection.enabled,
            "status": connection.status,
            "last_synced_at": (
                connection.last_synced_at.isoformat()
                if connection.last_synced_at is not None
                else None
            ),
            "last_error": connection.last_error,
        }
        for connection in connections
    ]


INTEGRATION_READ_TOOLS = [list_calendar_sync_status]
