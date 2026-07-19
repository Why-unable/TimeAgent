from apps.agents.tools.event_tools import EVENT_TOOLS
from apps.agents.tools.planning_tools import PLANNING_TOOLS
from apps.agents.tools.preference_tools import PREFERENCE_TOOLS
from apps.agents.tools.reminder_tools import REMINDER_TOOLS
from apps.agents.tools.task_tools import TASK_TOOLS
from apps.agents.tools.time_tools import TIME_TOOLS

READ_ONLY_TOOLS = [
    *TIME_TOOLS,
    *PREFERENCE_TOOLS,
    *EVENT_TOOLS[:3],
    *TASK_TOOLS[:2],
    *REMINDER_TOOLS[:2],
    *PLANNING_TOOLS,
]
WRITE_TOOLS = [*EVENT_TOOLS[3:], *TASK_TOOLS[2:], *REMINDER_TOOLS[2:]]
TIME_STEWARD_TOOLS = [*READ_ONLY_TOOLS, *WRITE_TOOLS]

__all__ = ["READ_ONLY_TOOLS", "TIME_STEWARD_TOOLS", "WRITE_TOOLS"]
