from apps.agents.tools.event_tools import EVENT_READ_TOOLS, EVENT_WRITE_TOOLS
from apps.agents.tools.handoff_tools import HANDOFF_TOOLS
from apps.agents.tools.planning_tools import PLANNING_READ_TOOLS, PLANNING_WRITE_TOOLS
from apps.agents.tools.reminder_tools import (
    REMINDER_READ_TOOLS,
    REMINDER_WRITE_TOOLS,
)
from apps.agents.tools.task_tools import TASK_READ_TOOLS, TASK_WRITE_TOOLS
from apps.agents.tools.time_tools import TIME_TOOLS

READ_ONLY_TOOLS = [
    *TIME_TOOLS,
    *EVENT_READ_TOOLS,
    *TASK_READ_TOOLS,
    *REMINDER_READ_TOOLS,
    *PLANNING_READ_TOOLS,
    *HANDOFF_TOOLS,
]
WRITE_TOOLS = [
    *EVENT_WRITE_TOOLS,
    *TASK_WRITE_TOOLS,
    *REMINDER_WRITE_TOOLS,
    *PLANNING_WRITE_TOOLS,
]
TIME_STEWARD_TOOLS = [*READ_ONLY_TOOLS, *WRITE_TOOLS]

__all__ = ["HANDOFF_TOOLS", "READ_ONLY_TOOLS", "TIME_STEWARD_TOOLS", "WRITE_TOOLS"]
