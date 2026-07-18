from datetime import datetime, time

from langchain.tools import ToolRuntime, tool

from apps.agents.context import RuntimeContext
from apps.agents.tools.common import require_actor
from apps.planning.schemas import PlanningConstraints
from apps.planning.services import PlanningService


@tool
def find_free_slots(
    range_start: datetime,
    range_end: datetime,
    duration_minutes: int,
    runtime: ToolRuntime[RuntimeContext],
    daily_start: time | None = None,
    daily_end: time | None = None,
    max_results: int = 10,
) -> list[dict[str, str]]:
    """Find deterministic free slots using events, planned tasks, timezone and work hours."""

    constraints = PlanningConstraints(
        timezone=runtime.context.timezone,
        daily_start=daily_start,
        daily_end=daily_end,
        max_results=max_results,
    )
    slots = PlanningService.find_free_slots(
        user=require_actor(runtime),
        range_start=range_start,
        range_end=range_end,
        duration_minutes=duration_minutes,
        constraints=constraints,
    )
    return [
        {"start_at": slot.start_at.isoformat(), "end_at": slot.end_at.isoformat()} for slot in slots
    ]


PLANNING_TOOLS = [find_free_slots]
