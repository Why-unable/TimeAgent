from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from langchain.tools import ToolRuntime, tool
from pydantic import AwareDatetime

from apps.agents.context import RuntimeContext
from apps.agents.tools.common import require_actor, require_writable
from apps.planning.adaptive import AdaptivePlanningService
from apps.planning.automation import AutomationPolicyService
from apps.planning.schemas import (
    DailyAvailabilityWindow,
    SchedulePlanItemEdit,
    TaskScheduleDecision,
)
from apps.planning.services import PlanningService
from apps.time_memory.decision_profile import DecisionProfileService


def _plan_items_with_local_times(
    items: list[dict[str, object]],
    *,
    timezone: str,
) -> list[dict[str, object]]:
    """Keep canonical UTC plan times and add user-local display values for the Agent."""
    user_timezone = ZoneInfo(timezone)

    def convert(value: object) -> object:
        if isinstance(value, list):
            return [convert(child) for child in value]
        if not isinstance(value, dict):
            return value

        result = {key: convert(child) for key, child in value.items()}
        for field in ("start_at", "end_at"):
            raw = value.get(field)
            if raw is None:
                continue
            if isinstance(raw, datetime):
                parsed = raw
            elif isinstance(raw, str):
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            else:
                continue
            if parsed.utcoffset() is None:
                raise ValueError(f"Schedule plan {field} must include a timezone")
            result[f"{field}_local"] = parsed.astimezone(user_timezone).isoformat()
        return result

    converted = convert(items)
    return converted if isinstance(converted, list) else []


@tool
def get_planning_context(
    range_start: AwareDatetime,
    range_end: AwareDatetime,
    runtime: ToolRuntime[RuntimeContext],
    mode: Literal["context", "free_slots"] = "context",
    duration_minutes: int | None = None,
    task_id: UUID | None = None,
    allowed_weekdays: list[int] | None = None,
    daily_worktime_overrides: list[DailyAvailabilityWindow] | None = None,
    one_slot_per_local_date: bool = False,
    max_free_slots: int = 10,
    reference_start_at: AwareDatetime | None = None,
    reference_end_at: AwareDatetime | None = None,
) -> dict[str, object]:
    """Read one planning view for a time range.

    Use ``context`` for selected tasks, calendar events, work hours and planning
    preferences, with canonical UTC timestamps and parallel ``*_local`` display
    timestamps in the user's IANA timezone. Use ``free_slots`` for availability or
    replan candidates; it returns deterministic time windows without event details. When
    finding slots for a specific existing task, pass ``task_id``; the service derives its
    duration, deadline, original plan, and version from stored task facts, excludes its old
    interval from busy time, and returns the task facts with the candidates.
    Pass ``daily_worktime_overrides`` when the user gives date-bounded working hours; those
    hours apply only on the inclusive local dates, and ordinary work hours apply otherwise.
    Set ``one_slot_per_local_date`` when comparing a task's fit across multiple days; the
    service then returns at most the earliest valid candidate on each local date, up to
    ``max_free_slots``, instead of filling the result with many 15-minute variants from one day.
    For minimum-churn replanning, pass the existing planned start and end as the reference
    range; results are ranked by total movement minutes, lowest first.
    If its duration is
    omitted, the user's Runtime default event duration is used. The required range
    arguments are named exactly ``range_start`` and ``range_end``; do not use
    ``starts_after`` or ``ends_before``. Before recommending a specific task move,
    query ``free_slots`` with that task's duration and the applicable date bounds.
    """

    selected_duration = duration_minutes
    if mode == "free_slots" and selected_duration is None:
        selected_duration = runtime.context.planning_preferences.default_event_duration_minutes

    return PlanningService.get_planning_context(
        user=require_actor(runtime),
        range_start=range_start,
        range_end=range_end,
        mode=mode,
        duration_minutes=selected_duration,
        task_id=task_id,
        allowed_weekdays=allowed_weekdays,
        daily_worktime_overrides=daily_worktime_overrides,
        one_slot_per_local_date=one_slot_per_local_date,
        max_free_slots=max_free_slots,
        reference_start_at=reference_start_at,
        reference_end_at=reference_end_at,
        not_before=(runtime.context.current_datetime if mode == "free_slots" else None),
    )


@tool
def propose_schedule_plan(
    task_ids: list[UUID],
    range_start: AwareDatetime,
    range_end: AwareDatetime,
    runtime: ToolRuntime[RuntimeContext],
    strategy: str = "plan_tasks_only",
    allowed_weekdays: list[int] | None = None,
    max_daily_minutes: int | None = None,
    daily_worktime_overrides: list[DailyAvailabilityWindow] | None = None,
    task_decisions: list[TaskScheduleDecision] | None = None,
) -> dict[str, object]:
    """Create a reviewable draft and include structured decisions for selected tasks.

    Preferred starts are soft goals. Explicit/confirmed date bounds, predecessor
    links, minimum gaps, date-bounded daily availability windows and a requested
    daily task-minute cap are validated as hard constraints. Use daily_worktime_overrides
    when the user gives a temporary daily time restriction that later changes. The
    draft is not applied. Create one draft per request; use its plan_id and
    edit_schedule_plan for refinements instead of proposing a replacement draft. Returned
    UTC start/end values have parallel user-local fields.
    """

    actor = require_writable(runtime)
    decision_profile_snapshot: dict[str, object] = {
        "status": "unavailable",
        "reason": "agent_store_unavailable",
    }
    if runtime.store is not None:
        decision_profile_snapshot = DecisionProfileService.get(
            user=actor,
            store=runtime.store,
        ).as_dict()
    plan = PlanningService.propose_schedule_plan(
        user=actor,
        task_ids=task_ids,
        range_start=range_start,
        range_end=range_end,
        strategy=strategy,
        allowed_weekdays=allowed_weekdays,
        max_daily_minutes=max_daily_minutes,
        daily_worktime_overrides=daily_worktime_overrides,
        task_decisions=task_decisions,
        decision_profile_snapshot=decision_profile_snapshot,
        now=runtime.context.current_datetime,
    )
    raw_plan_evidence: object = next(
        (item.get("evidence") for item in plan.items if item.get("kind") == "plan_evidence"),
        {},
    )
    plan_evidence = raw_plan_evidence if isinstance(raw_plan_evidence, dict) else {}
    creation_validation: object = plan_evidence.get("creation_validation", {})
    return {
        "plan_id": str(plan.pk),
        "version": plan.version,
        "strategy": plan.strategy,
        "validation": creation_validation,
        "items": _plan_items_with_local_times(
            plan.items,
            timezone=runtime.context.timezone,
        ),
    }


@tool
def compare_schedule_plans(
    task_ids: list[UUID],
    range_start: AwareDatetime,
    range_end: AwareDatetime,
    runtime: ToolRuntime[RuntimeContext],
    strategy: str = "plan_tasks_only",
    allowed_weekdays: list[int] | None = None,
    max_daily_minutes: int | None = None,
    daily_worktime_overrides: list[DailyAvailabilityWindow] | None = None,
    task_decisions: list[TaskScheduleDecision] | None = None,
) -> dict[str, object]:
    """Compare draft orderings; UTC schedule times include parallel user-local fields."""

    actor = require_writable(runtime)
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
        allowed_weekdays=allowed_weekdays,
        max_daily_minutes=max_daily_minutes,
        daily_worktime_overrides=daily_worktime_overrides,
        task_decisions=task_decisions,
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
                "items": _plan_items_with_local_times(
                    plan.items,
                    timezone=runtime.context.timezone,
                ),
            }
            for plan in result.alternatives
        ],
        "comparison": list(result.comparison),
    }


@tool
def detect_schedule_disruptions(
    range_start: AwareDatetime,
    range_end: AwareDatetime,
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
def edit_schedule_plan(
    plan_id: UUID,
    expected_version: int,
    edits: list[SchedulePlanItemEdit],
    runtime: ToolRuntime[RuntimeContext],
) -> dict[str, object]:
    """Revise one draft atomically; returned UTC schedule times include user-local fields.

    Include only tasks that actually need to move or change lock state; omit unchanged
    items. A moved item on the current Runtime-local date must start strictly after the
    Runtime current time, not merely at or after the day's work start.
    """

    plan = PlanningService.edit_schedule_plan(
        user=require_writable(runtime),
        plan_id=plan_id,
        expected_version=expected_version,
        edits=[edit.model_dump(exclude_none=True) for edit in edits],
        now=runtime.context.current_datetime,
    )
    return {
        "plan_id": str(plan.pk),
        "version": plan.version,
        "status": plan.status,
        "items": _plan_items_with_local_times(
            plan.items,
            timezone=runtime.context.timezone,
        ),
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
    blocked_start: AwareDatetime,
    blocked_end: AwareDatetime,
    movable_task_ids: list[UUID],
    horizon_end: AwareDatetime,
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
    get_planning_context,
    propose_schedule_plan,
    compare_schedule_plans,
    detect_schedule_disruptions,
    list_automation_policies,
]
PLANNING_WRITE_TOOLS = [
    validate_schedule_plan,
    edit_schedule_plan,
    abandon_schedule_plan,
    apply_schedule_plan,
    apply_local_replan,
]
PLANNING_TOOLS = [*PLANNING_READ_TOOLS, *PLANNING_WRITE_TOOLS]
