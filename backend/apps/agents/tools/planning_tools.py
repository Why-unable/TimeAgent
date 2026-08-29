from datetime import datetime, time
from uuid import UUID

from langchain.tools import ToolRuntime, tool

from apps.agents.context import RuntimeContext
from apps.agents.tools.common import require_actor, require_writable
from apps.planning.adaptive import AdaptivePlanningService
from apps.planning.automation import AutomationPolicyService
from apps.planning.schemas import PlanningConstraints
from apps.planning.services import PlanningService
from apps.time_memory.decision_profile import DecisionProfileService


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

    decision_profile_snapshot: dict[str, object] = {
        "status": "unavailable",
        "reason": "agent_store_unavailable",
    }
    if runtime.store is not None:
        decision_profile_snapshot = DecisionProfileService.get(
            user=require_actor(runtime),
            store=runtime.store,
        ).as_dict()
    plan = PlanningService.propose_schedule_plan(
        user=require_actor(runtime),
        task_ids=task_ids,
        range_start=range_start,
        range_end=range_end,
        strategy=strategy,
        decision_profile_snapshot=decision_profile_snapshot,
        now=runtime.context.current_datetime,
    )
    return {
        "plan_id": str(plan.pk),
        "version": plan.version,
        "strategy": plan.strategy,
        "items": plan.items,
    }


@tool
def compare_schedule_plans(
    task_ids: list[UUID],
    range_start: datetime,
    range_end: datetime,
    runtime: ToolRuntime[RuntimeContext],
    strategy: str = "plan_tasks_only",
) -> dict[str, object]:
    """Create two named deterministic draft alternatives without claiming an optimum."""

    actor = require_actor(runtime)
    snapshot: dict[str, object] = {
        "status": "unavailable",
        "reason": "agent_store_unavailable",
    }
    if runtime.store is not None:
        snapshot = DecisionProfileService.get(user=actor, store=runtime.store).as_dict()
    result = PlanningService.compare_schedule_plans(
        user=actor,
        task_ids=task_ids,
        range_start=range_start,
        range_end=range_end,
        strategy=strategy,
        decision_profile_snapshot=snapshot,
        now=runtime.context.current_datetime,
    )
    return {
        "claim": result.claim,
        "alternatives": [
            {
                "plan_id": str(plan.pk),
                "version": plan.version,
                "strategy": plan.strategy,
                "items": plan.items,
            }
            for plan in result.alternatives
        ],
        "comparison": list(result.comparison),
    }


@tool
def detect_schedule_disruptions(
    range_start: datetime,
    range_end: datetime,
    runtime: ToolRuntime[RuntimeContext],
) -> list[dict[str, object]]:
    """Detect factual overlaps between planned tasks and current calendar events."""

    return [
        {
            "task_id": str(item.task_id),
            "task_title": item.task_title,
            "task_version": item.task_version,
            "event_id": str(item.event_id),
            "event_title": item.event_title,
            "blocked_start": item.blocked_start.isoformat(),
            "blocked_end": item.blocked_end.isoformat(),
            "overlap_minutes": item.overlap_minutes,
            "reason_codes": list(item.reason_codes),
        }
        for item in AdaptivePlanningService.detect_disruptions(
            user=require_actor(runtime),
            range_start=range_start,
            range_end=range_end,
        )
    ]


@tool
def list_automation_policies(
    runtime: ToolRuntime[RuntimeContext],
) -> list[dict[str, object]]:
    """List the current user's explicit task-rescheduling authorization policies."""

    return [
        {
            "policy_id": str(policy.pk),
            "name": policy.name,
            "enabled": policy.enabled,
            "allow_task_reschedule": policy.allow_task_reschedule,
            "max_moves_per_run": policy.max_moves_per_run,
            "requires_approval": policy.requires_approval,
            "authorized_task_ids": policy.authorized_task_ids,
        }
        for policy in AutomationPolicyService.list(user=require_actor(runtime))
    ]


@tool
def validate_schedule_plan(
    plan_id: UUID,
    expected_version: int,
    runtime: ToolRuntime[RuntimeContext],
) -> dict[str, object]:
    """Revalidate a draft against current facts and persist invalidation when stale."""

    result = PlanningService.validate_schedule_plan(
        user=require_writable(runtime),
        plan_id=plan_id,
        expected_version=expected_version,
        now=runtime.context.current_datetime,
    )
    return {
        "plan_id": str(result.plan.pk),
        "version": result.plan.version,
        "status": result.plan.status,
        "valid": result.is_valid,
        "reason_codes": list(result.reason_codes),
        "checked_at": result.checked_at.isoformat(),
    }


@tool
def set_schedule_plan_item_lock(
    plan_id: UUID,
    expected_version: int,
    task_id: UUID,
    locked: bool,
    runtime: ToolRuntime[RuntimeContext],
) -> dict[str, object]:
    """Lock or unlock one draft item without changing task or calendar facts."""

    plan = PlanningService.edit_schedule_plan(
        user=require_writable(runtime),
        plan_id=plan_id,
        expected_version=expected_version,
        edits=[{"task_id": str(task_id), "locked": locked}],
        now=runtime.context.current_datetime,
    )
    return {
        "plan_id": str(plan.pk),
        "version": plan.version,
        "status": plan.status,
        "task_id": str(task_id),
        "locked": locked,
    }


@tool
def abandon_schedule_plan(
    plan_id: UUID,
    expected_version: int,
    runtime: ToolRuntime[RuntimeContext],
) -> dict[str, object]:
    """Abandon one versioned draft without changing task or calendar facts."""

    plan = PlanningService.abandon_schedule_plan(
        user=require_writable(runtime),
        plan_id=plan_id,
        expected_version=expected_version,
        now=runtime.context.current_datetime,
    )
    return {"plan_id": str(plan.pk), "version": plan.version, "status": plan.status}


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
        now=runtime.context.current_datetime,
    )
    return {"plan_id": str(plan.pk), "status": plan.status, "version": plan.version}


@tool
def apply_local_replan(
    policy_id: UUID,
    blocked_start: datetime,
    blocked_end: datetime,
    movable_task_ids: list[UUID],
    horizon_end: datetime,
    operation_id: UUID,
    runtime: ToolRuntime[RuntimeContext],
) -> dict[str, object]:
    """Apply one bounded, reversible local task replan after HITL approval."""

    actor = require_writable(runtime)
    policy = AutomationPolicyService.get(user=actor, policy_id=policy_id)
    preview = AdaptivePlanningService.preview_local_replan(
        user=actor,
        blocked_start=blocked_start,
        blocked_end=blocked_end,
        movable_task_ids=movable_task_ids,
        horizon_end=horizon_end,
    )
    batch = AdaptivePlanningService.apply_local_replan(
        user=actor,
        policy=policy,
        preview=preview,
        operation_id=operation_id,
        approved=True,
    )
    return {
        "change_batch_id": str(batch.pk),
        "status": batch.status,
        "moved_count": len(batch.after_snapshot),
        "operation_id": str(batch.operation_id),
    }


PLANNING_READ_TOOLS = [
    find_free_slots,
    propose_schedule_plan,
    compare_schedule_plans,
    detect_schedule_disruptions,
    list_automation_policies,
]
PLANNING_WRITE_TOOLS = [
    validate_schedule_plan,
    set_schedule_plan_item_lock,
    abandon_schedule_plan,
    apply_schedule_plan,
    apply_local_replan,
]
PLANNING_TOOLS = [*PLANNING_READ_TOOLS, *PLANNING_WRITE_TOOLS]
