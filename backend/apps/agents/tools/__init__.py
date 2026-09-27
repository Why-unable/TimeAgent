from apps.agents.tools.decision_tools import DECISION_READ_TOOLS, DECISION_WRITE_TOOLS
from apps.agents.tools.event_tools import EVENT_READ_TOOLS, EVENT_WRITE_TOOLS
from apps.agents.tools.handoff_tools import HANDOFF_TOOLS as _HANDOFF_TOOLS
from apps.agents.tools.insight_tools import INSIGHT_READ_TOOLS, INSIGHT_WRITE_TOOLS
from apps.agents.tools.integration_tools import INTEGRATION_READ_TOOLS
from apps.agents.tools.manifest import ToolSpec, build_tool_manifest
from apps.agents.tools.memory_tools import MEMORY_READ_TOOLS, MEMORY_WRITE_TOOLS
from apps.agents.tools.planning_tools import PLANNING_READ_TOOLS, PLANNING_WRITE_TOOLS
from apps.agents.tools.reminder_tools import REMINDER_READ_TOOLS, REMINDER_WRITE_TOOLS
from apps.agents.tools.task_tools import TASK_READ_TOOLS, TASK_WRITE_TOOLS
from apps.agents.tools.time_tools import TIME_TOOLS

TOOL_MANIFEST: tuple[ToolSpec, ...] = build_tool_manifest(
    [
        ("time", "read", TIME_TOOLS),
        ("calendar", "read", EVENT_READ_TOOLS),
        ("calendar", "write", EVENT_WRITE_TOOLS),
        ("tasks", "read", TASK_READ_TOOLS),
        ("tasks", "write", TASK_WRITE_TOOLS),
        ("reminders", "read", REMINDER_READ_TOOLS),
        ("reminders", "write", REMINDER_WRITE_TOOLS),
        ("planning", "read", PLANNING_READ_TOOLS),
        ("planning", "write", PLANNING_WRITE_TOOLS),
        ("decision", "read", DECISION_READ_TOOLS),
        ("decision", "write", DECISION_WRITE_TOOLS),
        ("integrations", "read", INTEGRATION_READ_TOOLS),
        ("insights", "read", INSIGHT_READ_TOOLS),
        ("insights", "write", INSIGHT_WRITE_TOOLS),
        ("memory", "read", MEMORY_READ_TOOLS),
        ("memory", "write", MEMORY_WRITE_TOOLS),
        ("briefing", "read", _HANDOFF_TOOLS),
    ]
)
TOOL_SPECS = {spec.tool.name: spec for spec in TOOL_MANIFEST}
TIME_STEWARD_TOOLS = [spec.tool for spec in TOOL_MANIFEST]
READ_ONLY_TOOLS = [spec.tool for spec in TOOL_MANIFEST if "read" in spec.run_modes]
WRITE_TOOLS = [spec.tool for spec in TOOL_MANIFEST if "write" in spec.run_modes]
HANDOFF_TOOLS = [spec.tool for spec in TOOL_MANIFEST if spec.effect == "handoff"]
RETRY_SAFE_TOOLS = [spec.tool for spec in TOOL_MANIFEST if spec.retry_safe]

__all__ = [
    "HANDOFF_TOOLS",
    "READ_ONLY_TOOLS",
    "RETRY_SAFE_TOOLS",
    "TIME_STEWARD_TOOLS",
    "TOOL_MANIFEST",
    "TOOL_SPECS",
    "ToolSpec",
    "WRITE_TOOLS",
]
