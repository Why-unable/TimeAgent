from datetime import datetime, time
from uuid import UUID

from langchain.tools import ToolRuntime, tool

from apps.agents.context import RuntimeContext
from apps.agents.tools.common import require_actor, require_writable
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


@tool
def propose_schedule_plan(
    task_ids: list[UUID],
    range_start: datetime,
    range_end: datetime,
    runtime: ToolRuntime[RuntimeContext],
    strategy: str = "plan_tasks_only",
) -> dict[str, object]:
    """Create a persistent scheduling draft; it makes no task or calendar change."""

    plan = PlanningService.propose_schedule_plan(
        user=require_actor(runtime),
        task_ids=task_ids,
        range_start=range_start,
        range_end=range_end,
        strategy=strategy,
    )
    return {
        "plan_id": str(plan.pk),
        "version": plan.version,
        "strategy": plan.strategy,
        "items": plan.items,
    }


@tool
def apply_schedule_plan(
    plan_id: UUID,
    expected_version: int,
    runtime: ToolRuntime[RuntimeContext],
) -> dict[str, object]:
    """Apply a reviewed schedule plan atomically after one approval."""

    plan = PlanningService.apply_schedule_plan(
        user=require_writable(runtime),
        plan_id=plan_id,
        expected_version=expected_version,
        origin="agent",
    )
    return {"plan_id": str(plan.pk), "status": plan.status, "version": plan.version}


PLANNING_READ_TOOLS = [find_free_slots, propose_schedule_plan]
PLANNING_WRITE_TOOLS = [apply_schedule_plan]
PLANNING_TOOLS = [*PLANNING_READ_TOOLS, *PLANNING_WRITE_TOOLS]
