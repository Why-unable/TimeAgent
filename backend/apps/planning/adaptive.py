from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from apps.events.models import CalendarEvent, CalendarEventStatus
from apps.planning.models import (
    AutomationPolicy,
    ScheduleChangeBatch,
    ScheduleChangeBatchStatus,
)
from apps.planning.schemas import PlanningConstraints
from apps.planning.services import PlanningService
from apps.tasks.models import Task
from apps.tasks.services import TaskService
from common.database_locks import lock_user_schedule_writes
from common.time import to_utc


@dataclass(frozen=True, slots=True)
class LocalReplanPreview:
    """A review-only, bounded replan; it never mutates schedule facts."""

    blocked_start: datetime
    blocked_end: datetime
    moved_items: list[dict[str, object]]
    unchanged_task_ids: list[str]
    stability_cost: dict[str, int]
    reason: str


@dataclass(frozen=True, slots=True)
class ScheduleDisruption:
    task_id: UUID
    task_title: str
    task_version: int
    event_id: UUID
    event_title: str
    blocked_start: datetime
    blocked_end: datetime
    overlap_minutes: int
    reason_codes: tuple[str, ...]


class AdaptivePlanningService:
    @staticmethod
    def find_change_batch(
        *, user: User, operation_id: UUID
    ) -> ScheduleChangeBatch | None:
        return ScheduleChangeBatch.objects.filter(
            user=user,
            operation_id=operation_id,
        ).first()

    @staticmethod
    def detect_disruptions(
        *,
        user: User,
        range_start: datetime,
        range_end: datetime,
    ) -> list[ScheduleDisruption]:
        start = to_utc(range_start)
        end = to_utc(range_end)
        if end <= start:
            raise ValueError("range_end must be later than range_start")
        tasks = Task.objects.filter(
            user=user,
            status__in=("pending", "in_progress"),
            planned_start_at__lt=end,
            planned_end_at__gt=start,
        ).order_by("planned_start_at", "id")
        events = list(
            CalendarEvent.objects.filter(
                user=user,
                status__in=(CalendarEventStatus.CONFIRMED, CalendarEventStatus.TENTATIVE),
                start_at__lt=end,
                end_at__gt=start,
            ).order_by("start_at", "id")
        )
        disruptions: list[ScheduleDisruption] = []
        for task in tasks:
            if task.planned_start_at is None or task.planned_end_at is None:
                continue
            for event in events:
                if event.task_id == task.pk:
                    continue
                overlap_start = max(to_utc(task.planned_start_at), to_utc(event.start_at))
                overlap_end = min(to_utc(task.planned_end_at), to_utc(event.end_at))
                if overlap_end <= overlap_start:
                    continue
                disruptions.append(
                    ScheduleDisruption(
                        task_id=task.pk,
                        task_title=task.title,
                        task_version=task.version,
                        event_id=event.pk,
                        event_title=event.title,
                        blocked_start=overlap_start,
                        blocked_end=overlap_end,
                        overlap_minutes=max(
                            1, int((overlap_end - overlap_start).total_seconds() // 60)
                        ),
                        reason_codes=("calendar_event_overlaps_planned_task",),
                    )
                )
        return disruptions

    @staticmethod
    def preview_local_replan(
        *,
        user: User,
        blocked_start: datetime,
        blocked_end: datetime,
        movable_task_ids: list[UUID],
        horizon_end: datetime,
    ) -> LocalReplanPreview:
        start = to_utc(blocked_start)
        end = to_utc(blocked_end)
        horizon = to_utc(horizon_end)
        if end <= start:
            raise ValueError("blocked_end must be later than blocked_start")
        if horizon <= end:
            raise ValueError("horizon_end must be later than blocked_end")
        if not movable_task_ids or len(set(movable_task_ids)) != len(movable_task_ids):
            raise ValueError("Provide unique movable task IDs")
        tasks = list(
            Task.objects.filter(
                user=user,
                pk__in=movable_task_ids,
                status__in=("pending", "in_progress"),
                planned_start_at__lt=end,
                planned_end_at__gt=start,
            )
        )
        if len(tasks) != len(movable_task_ids):
            raise ValueError("Every movable task must overlap the blocked interval")
        task_by_id = {task.pk: task for task in tasks}
        tasks = [task_by_id[task_id] for task_id in movable_task_ids]
        moved_items: list[dict[str, object]] = []
        assigned: list[tuple[datetime, datetime]] = []
        unchanged_task_ids: list[str] = []
        for task in tasks:
            if task.planned_start_at is None or task.planned_end_at is None:
                raise ValueError("Every movable task must have a planned interval")
            duration = task.estimated_minutes or 30
            slots = PlanningService.find_free_slots(
                user=user,
                range_start=end,
                range_end=min(horizon, task.due_at or horizon),
                duration_minutes=duration,
                constraints=PlanningConstraints(max_results=256),
            )
            slot = next(
                (
                    candidate
                    for candidate in slots
                    if not any(
                        candidate.start_at < assigned_end and candidate.end_at > assigned_start
                        for assigned_start, assigned_end in assigned
                    )
                ),
                None,
            )
            if slot is None:
                moved_items.append(
                    {
                        "task_id": str(task.pk),
                        "state": "unplaced",
                        "reason_codes": ["insufficient_free_capacity"],
                    }
                )
                unchanged_task_ids.append(str(task.pk))
                continue
            assigned.append((slot.start_at, slot.end_at))
            moved_items.append(
                {
                    "task_id": str(task.pk),
                    "task_version": task.version,
                    "state": "moved",
                    "from_start_at": task.planned_start_at.astimezone(UTC).isoformat(),
                    "from_end_at": task.planned_end_at.astimezone(UTC).isoformat(),
                    "to_start_at": slot.start_at.isoformat(),
                    "to_end_at": (slot.start_at + timedelta(minutes=duration)).isoformat(),
                    "reason_codes": ["blocked_interval"],
                }
            )
        moved = [item for item in moved_items if item.get("state") == "moved"]
        movement_minutes = [
            int(
                abs(
                    (
                        datetime.fromisoformat(str(item["to_start_at"]))
                        - datetime.fromisoformat(str(item["from_start_at"]))
                    ).total_seconds()
                )
                // 60
            )
            for item in moved
        ]
        return LocalReplanPreview(
            blocked_start=start,
            blocked_end=end,
            moved_items=moved_items,
            unchanged_task_ids=unchanged_task_ids,
            stability_cost={
                "moved_count": len(moved),
                "total_move_minutes": sum(movement_minutes),
                "max_move_minutes": max(movement_minutes, default=0),
                "unplaced_count": len(unchanged_task_ids),
            },
            reason="bounded_local_replan_requires_explicit_movable_ids",
        )

    @staticmethod
    @transaction.atomic
    def apply_local_replan(
        *,
        user: User,
        policy: AutomationPolicy,
        preview: LocalReplanPreview,
        operation_id: UUID,
        approved: bool = False,
    ) -> ScheduleChangeBatch:
        if policy.user_id != user.pk or not policy.enabled or not policy.allow_task_reschedule:
            raise PermissionError("Automation policy does not allow task rescheduling")
        if policy.requires_approval and not approved:
            raise PermissionError("This automation policy requires explicit approval")
        lock_user_schedule_writes(user)
        existing = ScheduleChangeBatch.objects.filter(
            user=user,
            operation_id=operation_id,
        ).first()
        if existing is not None:
            if existing.policy_id != policy.pk:
                raise ValueError("Operation ID was already used with another automation policy")
            return existing
        moved = [item for item in preview.moved_items if item.get("state") == "moved"]
        if not moved:
            raise ValueError("Local replan has no movable results")
        if len(moved) > policy.max_moves_per_run:
            raise ValueError("Local replan exceeds the automation policy move limit")
        authorized = set(policy.authorized_task_ids)
        moved_ids = {str(item["task_id"]) for item in moved}
        if authorized and not moved_ids.issubset(authorized):
            raise PermissionError("Local replan contains a task outside the policy allowlist")
        locked_tasks: dict[str, Task] = {}
        proposed_slots: list[tuple[UUID, datetime, datetime]] = []
        for item in moved:
            task = Task.objects.select_for_update().get(pk=str(item["task_id"]), user=user)
            if task.version != item.get("task_version"):
                raise ValueError(f"Task {task.pk} changed since preview")
            locked_tasks[str(task.pk)] = task
            proposed_slots.append(
                (
                    task.pk,
                    datetime.fromisoformat(str(item["to_start_at"])),
                    datetime.fromisoformat(str(item["to_end_at"])),
                )
            )
        PlanningService.validate_task_slots(user=user, slots=proposed_slots)
        before: list[dict[str, object]] = []
        after: list[dict[str, object]] = []
        batch = ScheduleChangeBatch.objects.create(
            user=user,
            policy=policy,
            operation_id=operation_id,
            before_snapshot=before,
            after_snapshot=after,
        )
        for item in moved:
            task = locked_tasks[str(item["task_id"])]
            before.append(
                {
                    "task_id": str(task.pk),
                    "version": task.version,
                    "start_at": task.planned_start_at.isoformat()
                    if task.planned_start_at
                    else None,
                    "end_at": task.planned_end_at.isoformat() if task.planned_end_at else None,
                }
            )
            updated = TaskService.reschedule_task(
                task_id=task.pk,
                user=user,
                planned_start_at=datetime.fromisoformat(str(item["to_start_at"])),
                planned_end_at=datetime.fromisoformat(str(item["to_end_at"])),
                origin="adaptive_local_replan",
            )
            if updated.planned_start_at is None or updated.planned_end_at is None:
                raise RuntimeError("Reschedule service returned an unplanned task")
            after.append(
                {
                    "task_id": str(updated.pk),
                    "version": updated.version,
                    "start_at": updated.planned_start_at.isoformat(),
                    "end_at": updated.planned_end_at.isoformat(),
                }
            )
        batch.before_snapshot = before
        batch.after_snapshot = after
        batch.status = ScheduleChangeBatchStatus.APPLIED
        batch.applied_at = timezone.now()
        batch.save(update_fields=["before_snapshot", "after_snapshot", "status", "applied_at"])
        return batch

    @staticmethod
    @transaction.atomic
    def revert_batch(*, user: User, batch_id: UUID) -> ScheduleChangeBatch:
        batch = ScheduleChangeBatch.objects.select_for_update().get(pk=batch_id, user=user)
        if batch.status != ScheduleChangeBatchStatus.APPLIED:
            return batch
        for snapshot in batch.before_snapshot:
            task = Task.objects.select_for_update().get(pk=snapshot["task_id"], user=user)
            after_snapshot = next(
                item for item in batch.after_snapshot if item["task_id"] == snapshot["task_id"]
            )
            if task.version != after_snapshot["version"]:
                raise ValueError(f"Task {task.pk} changed after adaptive replan")
            TaskService.reschedule_task(
                task_id=task.pk,
                user=user,
                planned_start_at=(
                    datetime.fromisoformat(snapshot["start_at"])
                    if snapshot.get("start_at")
                    else None
                ),
                planned_end_at=(
                    datetime.fromisoformat(snapshot["end_at"]) if snapshot.get("end_at") else None
                ),
                origin="adaptive_local_replan_revert",
            )
        batch.status = ScheduleChangeBatchStatus.REVERTED
        batch.reverted_at = timezone.now()
        batch.save(update_fields=["status", "reverted_at"])
        return batch
