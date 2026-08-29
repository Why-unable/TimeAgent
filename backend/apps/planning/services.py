from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from apps.events.models import CalendarEvent, CalendarEventStatus
from apps.events.services import CreateEventCommand, EventService
from apps.planning.models import SchedulePlan, SchedulePlanStatus
from apps.planning.schemas import PlanningConstraints, TimeSlot
from apps.preferences.models import UserPreference
from apps.tasks.models import Task, TaskStatus
from apps.tasks.services import TaskService
from common.database_locks import lock_user_schedule_writes
from common.time import get_timezone, resolve_local_datetime, to_utc

BusyInterval = tuple[datetime, datetime]


@dataclass(frozen=True, slots=True)
class PlanComparison:
    alternatives: tuple[SchedulePlan, SchedulePlan]
    comparison: tuple[dict[str, object], dict[str, object]]
    claim: str


@dataclass(frozen=True, slots=True)
class PlanValidationResult:
    plan: SchedulePlan
    is_valid: bool
    reason_codes: tuple[str, ...]
    checked_at: datetime


class PlanningService:
    ORDERINGS = frozenset({"priority_deadline", "longest_first"})

    @staticmethod
    def list_schedule_plans(*, user: User, limit: int = 50) -> list[SchedulePlan]:
        if limit < 1 or limit > 200:
            raise ValueError("Schedule plan list limit must be between 1 and 200")
        return list(
            SchedulePlan.objects.filter(user=user).order_by("-created_at", "-id")[:limit]
        )

    @staticmethod
    def validate_task_slots(
        *,
        user: User,
        slots: Sequence[tuple[UUID, datetime, datetime]],
    ) -> None:
        if not slots:
            return
        normalized = [
            (task_id, to_utc(start_at), to_utc(end_at)) for task_id, start_at, end_at in slots
        ]
        for _task_id, start_at, end_at in normalized:
            if end_at <= start_at:
                raise ValueError("Proposed task slot has an invalid range")
        for index, (_task_id, start_at, end_at) in enumerate(normalized):
            if any(
                start_at < other_end and end_at > other_start
                for _, other_start, other_end in normalized[index + 1 :]
            ):
                raise ValueError("Proposed task slots overlap each other")
        task_ids = [task_id for task_id, _, _ in normalized]
        for _task_id, start_at, end_at in normalized:
            event_conflict = (
                CalendarEvent.objects.filter(
                    user=user,
                    start_at__lt=end_at,
                    end_at__gt=start_at,
                )
                .exclude(status=CalendarEventStatus.CANCELLED)
                .exists()
            )
            task_conflict = (
                Task.objects.filter(
                    user=user,
                    status__in=(TaskStatus.PENDING, TaskStatus.IN_PROGRESS),
                    planned_start_at__lt=end_at,
                    planned_end_at__gt=start_at,
                )
                .exclude(pk__in=task_ids)
                .exists()
            )
            if event_conflict or task_conflict:
                raise ValueError("Proposed task slot conflicts with current schedule facts")

    @staticmethod
    @transaction.atomic
    def propose_schedule_plan(
        *,
        user: User,
        task_ids: Sequence[UUID],
        range_start: datetime,
        range_end: datetime,
        strategy: str,
        ordering: str = "priority_deadline",
        decision_profile_snapshot: dict[str, object] | None = None,
        now: datetime | None = None,
    ) -> SchedulePlan:
        if strategy not in {"plan_tasks_only", "create_linked_event_blocks"}:
            raise ValueError("Unsupported planning strategy")
        if not task_ids or len(set(task_ids)) != len(task_ids):
            raise ValueError("Provide unique task IDs")
        if ordering not in PlanningService.ORDERINGS:
            raise ValueError("Unsupported planning ordering")
        tasks = list(Task.objects.filter(user=user, pk__in=task_ids))
        if len(tasks) != len(task_ids):
            raise ValueError("Every task must belong to the current user")
        range_start_utc = to_utc(range_start)
        range_end_utc = to_utc(range_end)
        if range_end_utc <= range_start_utc:
            raise ValueError("range_end must be later than range_start")
        tasks = PlanningService._ordered_tasks(tasks, ordering=ordering)
        items = PlanningService._build_plan_items(
            user=user,
            tasks=tasks,
            range_start=range_start_utc,
            range_end=range_end_utc,
            reserved=[],
            decision_profile_snapshot=decision_profile_snapshot or {},
            strategy=strategy,
        )
        items.append(
            PlanningService._plan_evidence(
                items=items,
                task_count=len(tasks),
                ordering=ordering,
                range_start=range_start_utc,
                range_end=range_end_utc,
            )
        )
        anchor = to_utc(now or timezone.now())
        return SchedulePlan.objects.create(
            user=user,
            strategy=strategy,
            items=items,
            constraints_snapshot=PlanningService._constraints_snapshot(
                user=user,
                task_ids=task_ids,
                range_start=range_start_utc,
                range_end=range_end_utc,
                strategy=strategy,
                ordering=ordering,
            ),
            decision_profile_snapshot=decision_profile_snapshot
            or {"status": "unavailable", "reason": "decision_profile_not_provided"},
            expires_at=anchor + timedelta(seconds=settings.SCHEDULE_PLAN_TTL_SECONDS),
        )

    @staticmethod
    @transaction.atomic
    def compare_schedule_plans(
        *,
        user: User,
        task_ids: Sequence[UUID],
        range_start: datetime,
        range_end: datetime,
        strategy: str,
        decision_profile_snapshot: dict[str, object] | None = None,
        now: datetime | None = None,
    ) -> PlanComparison:
        alternatives = [
            PlanningService.propose_schedule_plan(
                user=user,
                task_ids=task_ids,
                range_start=range_start,
                range_end=range_end,
                strategy=strategy,
                ordering=ordering,
                decision_profile_snapshot=decision_profile_snapshot,
                now=now,
            )
            for ordering in ("priority_deadline", "longest_first")
        ]
        return PlanComparison(
            alternatives=(alternatives[0], alternatives[1]),
            comparison=(
                PlanningService._plan_metrics(alternatives[0]),
                PlanningService._plan_metrics(alternatives[1]),
            ),
            claim="deterministic_alternatives_not_global_optimum",
        )

    @staticmethod
    @transaction.atomic
    def regenerate_schedule_plan(
        *,
        user: User,
        plan_id: UUID,
        expected_version: int,
        task_ids: Sequence[UUID],
        ordering: str,
        now: datetime | None = None,
    ) -> SchedulePlan:
        if ordering not in PlanningService.ORDERINGS:
            raise ValueError("Unsupported planning ordering")
        if not task_ids or len(set(task_ids)) != len(task_ids):
            raise ValueError("Provide unique task IDs")
        lock_user_schedule_writes(user)
        plan = SchedulePlan.objects.select_for_update().get(pk=plan_id, user=user)
        if plan.status != SchedulePlanStatus.DRAFT:
            raise ValueError("Schedule plan is no longer a draft")
        if plan.version != expected_version:
            raise ValueError("Schedule plan version conflict")
        anchor = to_utc(now or timezone.now())
        if plan.expires_at <= anchor:
            raise ValueError("Schedule plan has expired")
        evidence = next(
            (item["evidence"] for item in plan.items if item.get("kind") == "plan_evidence"),
            None,
        )
        if (
            not isinstance(evidence, dict)
            or not evidence.get("range_start")
            or not evidence.get("range_end")
        ):
            raise ValueError("Schedule plan does not contain regeneration context")
        selected = {str(task_id) for task_id in task_ids}
        existing_task_ids = {
            str(item["task_id"])
            for item in plan.items
            if item.get("kind") != "plan_evidence" and item.get("task_id")
        }
        if not selected.issubset(existing_task_ids):
            raise ValueError("Every regenerated task must belong to the plan")
        if any(
            item.get("locked") is True and str(item.get("task_id")) in selected
            for item in plan.items
        ):
            raise ValueError("Locked plan items cannot be regenerated")
        retained = [
            item
            for item in plan.items
            if item.get("kind") != "plan_evidence" and str(item.get("task_id")) not in selected
        ]
        reserved = [
            (
                datetime.fromisoformat(str(item["start_at"])),
                datetime.fromisoformat(str(item["end_at"])),
            )
            for item in retained
            if item.get("state") == "placed"
        ]
        tasks = list(Task.objects.filter(user=user, pk__in=task_ids))
        if len(tasks) != len(task_ids):
            raise ValueError("Every regenerated task must belong to the current user")
        tasks = PlanningService._ordered_tasks(tasks, ordering=ordering)
        regenerated = PlanningService._build_plan_items(
            user=user,
            tasks=tasks,
            range_start=datetime.fromisoformat(str(evidence["range_start"])),
            range_end=datetime.fromisoformat(str(evidence["range_end"])),
            reserved=reserved,
            decision_profile_snapshot=plan.decision_profile_snapshot,
            strategy=plan.strategy,
        )
        items = [*retained, *regenerated]
        items.append(
            PlanningService._plan_evidence(
                items=items,
                task_count=len(items),
                ordering=ordering,
                range_start=datetime.fromisoformat(str(evidence["range_start"])),
                range_end=datetime.fromisoformat(str(evidence["range_end"])),
                regenerated_task_ids=sorted(selected),
            )
        )
        plan.items = items
        plan.constraints_snapshot = {
            **plan.constraints_snapshot,
            "ordering": ordering,
            "last_regenerated_at": anchor.isoformat(),
        }
        plan.expires_at = anchor + timedelta(seconds=settings.SCHEDULE_PLAN_TTL_SECONDS)
        plan.version += 1
        plan.save(
            update_fields=[
                "items",
                "constraints_snapshot",
                "expires_at",
                "version",
                "updated_at",
            ]
        )
        return plan

    @staticmethod
    def _constraints_snapshot(
        *,
        user: User,
        task_ids: Sequence[UUID],
        range_start: datetime,
        range_end: datetime,
        strategy: str,
        ordering: str,
    ) -> dict[str, object]:
        preference = UserPreference.objects.filter(user=user).first() or UserPreference(user=user)
        return {
            "snapshot_version": "planning-constraints-v1",
            "range_start": range_start.isoformat(),
            "range_end": range_end.isoformat(),
            "strategy": strategy,
            "ordering": ordering,
            "timezone": preference.timezone,
            "workday_start": preference.workday_start.isoformat(),
            "workday_end": preference.workday_end.isoformat(),
            "task_ids": [str(task_id) for task_id in task_ids],
            "planning_rules": preference.planning_rules,
        }

    @staticmethod
    def _ordered_tasks(tasks: list[Task], *, ordering: str) -> list[Task]:
        priority_rank = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        if ordering == "longest_first":
            return sorted(
                tasks,
                key=lambda task: (
                    -(task.estimated_minutes or 30),
                    task.due_at or datetime.max.replace(tzinfo=UTC),
                    task.id,
                ),
            )
        return sorted(
            tasks,
            key=lambda task: (
                priority_rank.get(task.priority, 9),
                task.due_at or datetime.max.replace(tzinfo=UTC),
                task.created_at,
                task.id,
            ),
        )

    @staticmethod
    def _build_plan_items(
        *,
        user: User,
        tasks: list[Task],
        range_start: datetime,
        range_end: datetime,
        reserved: list[BusyInterval],
        decision_profile_snapshot: dict[str, object],
        strategy: str,
    ) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        assigned = list(reserved)
        for task in tasks:
            base_duration, duration, duration_source = PlanningService._planned_duration(
                task=task,
                decision_profile_snapshot=decision_profile_snapshot,
            )
            if task.planning_locked:
                items.append(
                    PlanningService._unplaced_item(
                        task=task,
                        reason="task_planning_locked",
                        base_duration=base_duration,
                        planned_duration=duration,
                        duration_source=duration_source,
                    )
                )
                continue
            buffer_before = task.buffer_before_minutes
            buffer_after = task.buffer_after_minutes
            reserved_duration = buffer_before + duration + buffer_after
            deadline = task.due_at.astimezone(UTC) if task.due_at else range_end
            candidate_end = min(range_end, deadline)
            if candidate_end <= range_start:
                items.append(
                    PlanningService._unplaced_item(
                        task=task,
                        reason="deadline_before_range",
                        base_duration=base_duration,
                        planned_duration=duration,
                        duration_source=duration_source,
                    )
                )
                continue
            slots = PlanningService.find_free_slots(
                user=user,
                range_start=range_start,
                range_end=candidate_end,
                duration_minutes=reserved_duration,
                constraints=PlanningConstraints(max_results=256),
            )
            selected = next(
                (
                    slot
                    for slot in slots
                    if not any(
                        slot.start_at < assigned_end and slot.end_at > assigned_start
                        for assigned_start, assigned_end in assigned
                    )
                ),
                None,
            )
            if selected is None:
                split_items = PlanningService._build_split_items(
                    user=user,
                    task=task,
                    range_start=range_start,
                    range_end=candidate_end,
                    duration=duration,
                    duration_source=duration_source,
                    base_duration=base_duration,
                    assigned=assigned,
                    decision_profile_snapshot=decision_profile_snapshot,
                    strategy=strategy,
                )
                if split_items:
                    items.extend(split_items)
                    assigned.extend(
                        (
                            datetime.fromisoformat(str(item["reserved_start_at"])),
                            datetime.fromisoformat(str(item["reserved_end_at"])),
                        )
                        for item in split_items
                    )
                    continue
                items.append(
                    PlanningService._unplaced_item(
                        task=task,
                        reason="insufficient_free_capacity",
                        base_duration=base_duration,
                        planned_duration=duration,
                        duration_source=duration_source,
                    )
                )
                continue
            start_at = selected.start_at + timedelta(minutes=buffer_before)
            end_at = start_at + timedelta(minutes=duration)
            reserved_end_at = selected.start_at + timedelta(minutes=reserved_duration)
            assigned.append((selected.start_at, reserved_end_at))
            items.append(
                {
                    "task_id": str(task.pk),
                    "task_version": task.version,
                    "state": "placed",
                    "start_at": start_at.isoformat(),
                    "end_at": end_at.isoformat(),
                    "reserved_start_at": selected.start_at.isoformat(),
                    "reserved_end_at": reserved_end_at.isoformat(),
                    "buffer_before_minutes": buffer_before,
                    "buffer_after_minutes": buffer_after,
                    "locked": False,
                    "base_duration_minutes": base_duration,
                    "planned_duration_minutes": duration,
                    "duration_source": duration_source,
                    "decision_profile_version": decision_profile_snapshot.get("version"),
                    "soft_reason_codes": (
                        ["high_confidence_duration_calibration"]
                        if duration_source == "decision_profile"
                        else []
                    ),
                    "reason_codes": [],
                    "segment_index": 1,
                    "segment_count": 1,
                }
            )
        return items

    @staticmethod
    def _build_split_items(
        *,
        user: User,
        task: Task,
        range_start: datetime,
        range_end: datetime,
        duration: int,
        duration_source: str,
        base_duration: int,
        assigned: list[BusyInterval],
        decision_profile_snapshot: dict[str, object],
        strategy: str,
    ) -> list[dict[str, object]]:
        if strategy != "create_linked_event_blocks" or not task.splittable:
            return []
        minimum = min(duration, task.minimum_chunk_minutes)
        remaining = duration
        local_assigned = list(assigned)
        segments: list[dict[str, object]] = []
        while remaining > 0:
            candidate_sizes = [
                size
                for size in range(remaining, minimum - 1, -15)
                if remaining - size == 0 or remaining - size >= minimum
            ]
            selected: tuple[datetime, datetime, int] | None = None
            for chunk_minutes in candidate_sizes:
                reserved_minutes = (
                    task.buffer_before_minutes + chunk_minutes + task.buffer_after_minutes
                )
                slots = PlanningService.find_free_slots(
                    user=user,
                    range_start=range_start,
                    range_end=range_end,
                    duration_minutes=reserved_minutes,
                    constraints=PlanningConstraints(max_results=256),
                )
                slot = next(
                    (
                        candidate
                        for candidate in slots
                        if not any(
                            candidate.start_at < assigned_end
                            and candidate.end_at > assigned_start
                            for assigned_start, assigned_end in local_assigned
                        )
                    ),
                    None,
                )
                if slot is not None:
                    selected = (slot.start_at, slot.end_at, chunk_minutes)
                    break
            if selected is None:
                return []
            reserved_start, reserved_end, chunk_minutes = selected
            start_at = reserved_start + timedelta(minutes=task.buffer_before_minutes)
            end_at = start_at + timedelta(minutes=chunk_minutes)
            local_assigned.append((reserved_start, reserved_end))
            segments.append(
                {
                    "task_id": str(task.pk),
                    "task_version": task.version,
                    "state": "placed",
                    "start_at": start_at.isoformat(),
                    "end_at": end_at.isoformat(),
                    "reserved_start_at": reserved_start.isoformat(),
                    "reserved_end_at": reserved_end.isoformat(),
                    "locked": False,
                    "base_duration_minutes": base_duration,
                    "planned_duration_minutes": chunk_minutes,
                    "duration_source": duration_source,
                    "decision_profile_version": decision_profile_snapshot.get("version"),
                    "buffer_before_minutes": task.buffer_before_minutes,
                    "buffer_after_minutes": task.buffer_after_minutes,
                    "soft_reason_codes": ["task_split_across_multiple_blocks"],
                    "reason_codes": [],
                }
            )
            remaining -= chunk_minutes
        for index, segment in enumerate(segments, start=1):
            segment["segment_index"] = index
            segment["segment_count"] = len(segments)
        return segments if len(segments) > 1 else []

    @staticmethod
    def _plan_evidence(
        *,
        items: list[dict[str, object]],
        task_count: int,
        ordering: str,
        range_start: datetime,
        range_end: datetime,
        regenerated_task_ids: list[str] | None = None,
    ) -> dict[str, object]:
        placed = sum(1 for item in items if item.get("state") == "placed")
        evidence: dict[str, object] = {
            "planner_version": "v2-deterministic",
            "ordering": ordering,
            "range_start": range_start.isoformat(),
            "range_end": range_end.isoformat(),
            "hard_constraints": [
                "existing_events",
                "existing_planned_tasks",
                "deadline",
                "work_hours",
            ],
            "task_count": task_count,
            "placed_count": placed,
            "unplaced_count": task_count - placed,
        }
        if regenerated_task_ids is not None:
            evidence["regenerated_task_ids"] = regenerated_task_ids
        return {"kind": "plan_evidence", "evidence": evidence}

    @staticmethod
    def _plan_metrics(plan: SchedulePlan) -> dict[str, object]:
        task_items = [item for item in plan.items if item.get("kind") != "plan_evidence"]
        placed = [item for item in task_items if item.get("state") == "placed"]
        raw_evidence: object = next(
            (
                item.get("evidence", {})
                for item in plan.items
                if item.get("kind") == "plan_evidence"
            ),
            {},
        )
        evidence = raw_evidence if isinstance(raw_evidence, dict) else {}
        return {
            "plan_id": str(plan.pk),
            "ordering": evidence.get("ordering"),
            "placed_count": len(placed),
            "unplaced_count": len(task_items) - len(placed),
            "hard_constraint_violations": 0,
        }

    @staticmethod
    def _unplaced_item(
        *,
        task: Task,
        reason: str,
        base_duration: int,
        planned_duration: int,
        duration_source: str,
    ) -> dict[str, object]:
        return {
            "task_id": str(task.pk),
            "task_version": task.version,
            "state": "unplaced",
            "locked": task.planning_locked,
            "base_duration_minutes": base_duration,
            "planned_duration_minutes": planned_duration,
            "duration_source": duration_source,
            "buffer_before_minutes": task.buffer_before_minutes,
            "buffer_after_minutes": task.buffer_after_minutes,
            "splittable": task.splittable,
            "minimum_chunk_minutes": task.minimum_chunk_minutes,
            "reason_codes": [reason],
        }

    @staticmethod
    def _planned_duration(
        *,
        task: Task,
        decision_profile_snapshot: dict[str, object],
    ) -> tuple[int, int, str]:
        base_duration = task.estimated_minutes or 30
        enabled = decision_profile_snapshot.get("enabled") is True
        confidence = decision_profile_snapshot.get("confidence")
        sample_count = decision_profile_snapshot.get("sample_count")
        multiplier = decision_profile_snapshot.get("duration_multiplier")
        if (
            enabled
            and isinstance(confidence, int | float)
            and not isinstance(confidence, bool)
            and confidence >= 0.6
            and isinstance(sample_count, int)
            and not isinstance(sample_count, bool)
            and sample_count >= 5
            and isinstance(multiplier, int | float)
            and not isinstance(multiplier, bool)
        ):
            bounded = max(0.25, min(4.0, float(multiplier)))
            return base_duration, max(1, round(base_duration * bounded)), "decision_profile"
        return base_duration, base_duration, "task_estimate_or_default"

    @staticmethod
    @transaction.atomic
    def edit_schedule_plan(
        *,
        user: User,
        plan_id: UUID,
        expected_version: int,
        edits: Sequence[dict[str, object]],
        now: datetime | None = None,
    ) -> SchedulePlan:
        if not edits:
            raise ValueError("Provide at least one plan item edit")
        anchor = to_utc(now or timezone.now())
        lock_user_schedule_writes(user)
        plan = SchedulePlan.objects.select_for_update().get(pk=plan_id, user=user)
        if plan.status != SchedulePlanStatus.DRAFT:
            raise ValueError("Schedule plan is no longer a draft")
        if plan.version != expected_version:
            raise ValueError("Schedule plan version conflict")
        if plan.expires_at <= anchor:
            raise ValueError("Schedule plan has expired")
        by_task = {
            str(item.get("task_id")): item
            for item in plan.items
            if item.get("kind") != "plan_evidence" and item.get("task_id")
        }
        edited_ids: set[str] = set()
        for edit in edits:
            task_id = str(edit.get("task_id", ""))
            if not task_id or task_id in edited_ids or task_id not in by_task:
                raise ValueError("Each edited task must appear once in the plan")
            edited_ids.add(task_id)
            item = by_task[task_id]
            moves_item = "start_at" in edit or "end_at" in edit
            if moves_item and ("start_at" not in edit or "end_at" not in edit):
                raise ValueError("Plan item start and end must be edited together")
            if item.get("locked") is True and moves_item and edit.get("locked") is not False:
                raise ValueError("Unlock a plan item before moving it")
            if moves_item:
                start_at = edit["start_at"]
                end_at = edit["end_at"]
                if not isinstance(start_at, datetime) or not isinstance(end_at, datetime):
                    raise ValueError("Plan item times must be datetimes")
                item["start_at"] = to_utc(start_at).isoformat()
                item["end_at"] = to_utc(end_at).isoformat()
                before = int(item.get("buffer_before_minutes", 0))
                after = int(item.get("buffer_after_minutes", 0))
                item["reserved_start_at"] = (
                    to_utc(start_at) - timedelta(minutes=before)
                ).isoformat()
                item["reserved_end_at"] = (
                    to_utc(end_at) + timedelta(minutes=after)
                ).isoformat()
                item["state"] = "placed"
                item["reason_codes"] = []
            if "locked" in edit:
                item["locked"] = bool(edit["locked"])
        plan.expires_at = anchor + timedelta(seconds=settings.SCHEDULE_PLAN_TTL_SECONDS)
        reason_codes = PlanningService._plan_validation_reason_codes(
            user=user,
            plan=plan,
            now=anchor,
        )
        if reason_codes:
            raise ValueError(f"Edited plan is invalid: {', '.join(reason_codes)}")
        plan.version += 1
        plan.constraints_snapshot = {
            **plan.constraints_snapshot,
            "last_edited_at": anchor.isoformat(),
        }
        plan.save(
            update_fields=[
                "items",
                "version",
                "constraints_snapshot",
                "expires_at",
                "updated_at",
            ]
        )
        return plan

    @staticmethod
    @transaction.atomic
    def validate_schedule_plan(
        *,
        user: User,
        plan_id: UUID,
        expected_version: int,
        now: datetime | None = None,
    ) -> PlanValidationResult:
        anchor = to_utc(now or timezone.now())
        lock_user_schedule_writes(user)
        plan = SchedulePlan.objects.select_for_update().get(pk=plan_id, user=user)
        if plan.version != expected_version:
            raise ValueError("Schedule plan version conflict")
        reason_codes = PlanningService._plan_validation_reason_codes(
            user=user,
            plan=plan,
            now=anchor,
        )
        if reason_codes and plan.status == SchedulePlanStatus.DRAFT:
            PlanningService._mark_plan_invalidated(
                plan=plan,
                reason=reason_codes[0],
                now=anchor,
            )
        return PlanValidationResult(
            plan=plan,
            is_valid=not reason_codes,
            reason_codes=reason_codes,
            checked_at=anchor,
        )

    @staticmethod
    @transaction.atomic
    def abandon_schedule_plan(
        *,
        user: User,
        plan_id: UUID,
        expected_version: int,
        now: datetime | None = None,
    ) -> SchedulePlan:
        anchor = to_utc(now or timezone.now())
        plan = SchedulePlan.objects.select_for_update().get(pk=plan_id, user=user)
        if plan.status != SchedulePlanStatus.DRAFT:
            raise ValueError("Only a draft schedule plan can be abandoned")
        if plan.version != expected_version:
            raise ValueError("Schedule plan version conflict")
        plan.status = SchedulePlanStatus.ABANDONED
        plan.abandoned_at = anchor
        plan.version += 1
        plan.save(update_fields=["status", "abandoned_at", "version", "updated_at"])
        return plan

    @staticmethod
    def apply_schedule_plan(
        *,
        user: User,
        plan_id: UUID,
        expected_version: int,
        origin: str = "web",
        now: datetime | None = None,
    ) -> SchedulePlan:
        PlanningService._ensure_persisted_user(user)
        anchor = to_utc(now or timezone.now())
        reason_codes: tuple[str, ...] = ()
        with transaction.atomic():
            lock_user_schedule_writes(user)
            plan = SchedulePlan.objects.select_for_update().get(pk=plan_id, user=user)
            if plan.status != SchedulePlanStatus.DRAFT:
                raise ValueError("Schedule plan is no longer a draft")
            if plan.version != expected_version:
                raise ValueError("Schedule plan version conflict")
            reason_codes = PlanningService._plan_validation_reason_codes(
                user=user,
                plan=plan,
                now=anchor,
            )
            if reason_codes:
                PlanningService._mark_plan_invalidated(
                    plan=plan,
                    reason=reason_codes[0],
                    now=anchor,
                )
            else:
                for item in plan.items:
                    if (
                        item.get("kind") == "plan_evidence"
                        or item.get("state", "placed") != "placed"
                    ):
                        continue
                    task = Task.objects.select_for_update().get(pk=item["task_id"], user=user)
                    start_at = datetime.fromisoformat(str(item["start_at"]))
                    end_at = datetime.fromisoformat(str(item["end_at"]))
                    if plan.strategy == "plan_tasks_only":
                        TaskService.reschedule_task(
                            task_id=task.pk,
                            user=user,
                            planned_start_at=start_at,
                            planned_end_at=end_at,
                            origin=origin,
                        )
                    else:
                        EventService.create_event(
                            CreateEventCommand(
                                user=user,
                                task=task,
                                title=task.title,
                                start_at=start_at,
                                end_at=end_at,
                                timezone=PlanningService._user_timezone(user),
                                origin=origin,
                            )
                        )
                plan.status = SchedulePlanStatus.APPLIED
                plan.version += 1
                plan.applied_at = anchor
                plan.save(
                    update_fields=["status", "version", "applied_at", "updated_at"]
                )
        if reason_codes:
            raise ValueError(f"Schedule plan invalid: {', '.join(reason_codes)}")
        return plan

    @staticmethod
    def _plan_validation_reason_codes(
        *,
        user: User,
        plan: SchedulePlan,
        now: datetime,
    ) -> tuple[str, ...]:
        if plan.status != SchedulePlanStatus.DRAFT:
            return ("plan_not_draft",)
        if plan.expires_at <= now:
            return ("plan_expired",)
        try:
            proposed_slots = [
                (
                    UUID(str(item["task_id"])),
                    datetime.fromisoformat(
                        str(item.get("reserved_start_at", item["start_at"]))
                    ),
                    datetime.fromisoformat(
                        str(item.get("reserved_end_at", item["end_at"]))
                    ),
                )
                for item in plan.items
                if item.get("kind") != "plan_evidence"
                and item.get("state", "placed") == "placed"
            ]
        except (KeyError, TypeError, ValueError):
            return ("invalid_plan_item",)
        task_ids = list({task_id for task_id, _, _ in proposed_slots})
        tasks = {task.pk: task for task in Task.objects.filter(user=user, pk__in=task_ids)}
        if len(tasks) != len(task_ids):
            return ("task_missing",)
        item_versions = {
            UUID(str(item["task_id"])): int(item["task_version"])
            for item in plan.items
            if item.get("kind") != "plan_evidence" and item.get("task_id")
        }
        if any(tasks[task_id].version != item_versions.get(task_id) for task_id in task_ids):
            return ("task_version_changed",)
        for item in plan.items:
            if item.get("kind") == "plan_evidence" or item.get("state", "placed") != "placed":
                continue
            task_id = UUID(str(item["task_id"]))
            end_at = datetime.fromisoformat(str(item["end_at"]))
            deadline = tasks[task_id].due_at
            if deadline is not None and end_at > deadline:
                return ("deadline_violation",)
        if not PlanningService._slots_respect_constraint_snapshot(
            slots=proposed_slots,
            snapshot=plan.constraints_snapshot,
        ):
            return ("work_hours_violation",)
        try:
            PlanningService.validate_task_slots(user=user, slots=proposed_slots)
        except ValueError:
            return ("schedule_conflict",)
        return ()

    @staticmethod
    def _slots_respect_constraint_snapshot(
        *,
        slots: Sequence[tuple[UUID, datetime, datetime]],
        snapshot: dict[str, object],
    ) -> bool:
        try:
            user_timezone = get_timezone(str(snapshot["timezone"]))
            workday_start = time.fromisoformat(str(snapshot["workday_start"]))
            workday_end = time.fromisoformat(str(snapshot["workday_end"]))
        except (KeyError, TypeError, ValueError):
            return False
        for _task_id, start_at, end_at in slots:
            local_start = to_utc(start_at).astimezone(user_timezone)
            local_end = to_utc(end_at).astimezone(user_timezone)
            if (
                local_start.date() != local_end.date()
                or local_start.time().replace(tzinfo=None) < workday_start
                or local_end.time().replace(tzinfo=None) > workday_end
                or local_start.weekday() >= 5
            ):
                return False
        return True

    @staticmethod
    def _mark_plan_invalidated(
        *,
        plan: SchedulePlan,
        reason: str,
        now: datetime,
    ) -> None:
        plan.status = SchedulePlanStatus.INVALIDATED
        plan.invalidation_reason = reason
        plan.invalidated_at = now
        plan.version += 1
        plan.save(
            update_fields=[
                "status",
                "invalidation_reason",
                "invalidated_at",
                "version",
                "updated_at",
            ]
        )

    @staticmethod
    def find_free_slots(
        *,
        user: User,
        range_start: datetime,
        range_end: datetime,
        duration_minutes: int,
        constraints: PlanningConstraints | None = None,
    ) -> list[TimeSlot]:
        PlanningService._ensure_persisted_user(user)
        range_start_utc = to_utc(range_start)
        range_end_utc = to_utc(range_end)
        if range_end_utc <= range_start_utc:
            raise ValueError("range_end must be later than range_start")
        if duration_minutes < 1 or duration_minutes > 1440:
            raise ValueError("duration_minutes must be between 1 and 1440")

        constraints = constraints or PlanningConstraints()
        constraints.validate()
        preference = UserPreference.objects.filter(user=user).first() or UserPreference(user=user)
        timezone_name = constraints.timezone or preference.timezone
        user_timezone = get_timezone(timezone_name)
        daily_start = constraints.daily_start or preference.workday_start
        daily_end = constraints.daily_end or preference.workday_end
        if daily_end <= daily_start:
            raise ValueError("daily_end must be later than daily_start")

        busy_intervals = PlanningService._load_busy_intervals(
            user=user,
            range_start=range_start_utc,
            range_end=range_end_utc,
            include_planned_tasks=constraints.include_planned_tasks,
        )
        duration = timedelta(minutes=duration_minutes)
        increment = timedelta(minutes=constraints.slot_increment_minutes)
        local_start_date = range_start_utc.astimezone(user_timezone).date()
        local_end_date = range_end_utc.astimezone(user_timezone).date()
        slots: list[TimeSlot] = []

        current_date = local_start_date
        while current_date <= local_end_date:
            if current_date.weekday() in constraints.allowed_weekdays:
                window_start, window_end = PlanningService._daily_window(
                    current_date=current_date,
                    daily_start=daily_start,
                    daily_end=daily_end,
                    timezone_name=timezone_name,
                    range_start=range_start_utc,
                    range_end=range_end_utc,
                )
                if window_start < window_end:
                    PlanningService._append_window_slots(
                        slots=slots,
                        window_start=window_start,
                        window_end=window_end,
                        busy_intervals=busy_intervals,
                        duration=duration,
                        increment=increment,
                        max_results=constraints.max_results,
                    )
                    if (
                        constraints.max_results is not None
                        and len(slots) >= constraints.max_results
                    ):
                        return slots
            current_date += timedelta(days=1)

        return slots

    @staticmethod
    def _load_busy_intervals(
        *,
        user: User,
        range_start: datetime,
        range_end: datetime,
        include_planned_tasks: bool,
    ) -> list[BusyInterval]:
        event_intervals = (
            CalendarEvent.objects.filter(
                user=user,
                start_at__lt=range_end,
                end_at__gt=range_start,
            )
            .exclude(status=CalendarEventStatus.CANCELLED)
            .values_list("start_at", "end_at")
        )
        intervals = list(event_intervals)
        if include_planned_tasks:
            task_intervals = Task.objects.filter(
                user=user,
                status__in=(TaskStatus.PENDING, TaskStatus.IN_PROGRESS),
                planned_start_at__lt=range_end,
                planned_end_at__gt=range_start,
            ).values_list("planned_start_at", "planned_end_at")
            intervals.extend(
                (start_at, end_at)
                for start_at, end_at in task_intervals
                if start_at is not None and end_at is not None
            )
        return PlanningService._merge_intervals(intervals)

    @staticmethod
    def _merge_intervals(intervals: list[BusyInterval]) -> list[BusyInterval]:
        merged: list[BusyInterval] = []
        for start_at, end_at in sorted(intervals):
            if not merged or start_at > merged[-1][1]:
                merged.append((start_at, end_at))
                continue
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end_at))
        return merged

    @staticmethod
    def _daily_window(
        *,
        current_date: date,
        daily_start: time,
        daily_end: time,
        timezone_name: str,
        range_start: datetime,
        range_end: datetime,
    ) -> BusyInterval:
        local_start = datetime.combine(current_date, daily_start)
        local_end = datetime.combine(current_date, daily_end)
        window_start = resolve_local_datetime(local_start, timezone_name, fold=0)
        window_end = resolve_local_datetime(local_end, timezone_name, fold=1)
        return max(window_start, range_start), min(window_end, range_end)

    @staticmethod
    def _append_window_slots(
        *,
        slots: list[TimeSlot],
        window_start: datetime,
        window_end: datetime,
        busy_intervals: list[BusyInterval],
        duration: timedelta,
        increment: timedelta,
        max_results: int | None,
    ) -> None:
        cursor = window_start
        for busy_start, busy_end in busy_intervals:
            if busy_end <= cursor:
                continue
            if busy_start >= window_end:
                break
            PlanningService._append_gap_slots(
                slots=slots,
                gap_start=cursor,
                gap_end=min(busy_start, window_end),
                duration=duration,
                increment=increment,
                max_results=max_results,
            )
            if max_results is not None and len(slots) >= max_results:
                return
            cursor = max(cursor, busy_end)
            if cursor >= window_end:
                return
        PlanningService._append_gap_slots(
            slots=slots,
            gap_start=cursor,
            gap_end=window_end,
            duration=duration,
            increment=increment,
            max_results=max_results,
        )

    @staticmethod
    def _append_gap_slots(
        *,
        slots: list[TimeSlot],
        gap_start: datetime,
        gap_end: datetime,
        duration: timedelta,
        increment: timedelta,
        max_results: int | None,
    ) -> None:
        candidate_start = gap_start
        while candidate_start + duration <= gap_end:
            slots.append(
                TimeSlot(
                    start_at=candidate_start.astimezone(UTC),
                    end_at=(candidate_start + duration).astimezone(UTC),
                )
            )
            if max_results is not None and len(slots) >= max_results:
                return
            candidate_start += increment

    @staticmethod
    def _ensure_persisted_user(user: User) -> None:
        if user.pk is None:
            raise ValueError("Planning user must be persisted")

    @staticmethod
    def _user_timezone(user: User) -> str:
        preference = UserPreference.objects.filter(user=user).first()
        return preference.timezone if preference is not None else UserPreference(user=user).timezone
