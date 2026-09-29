from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from django.contrib.auth.models import User

from apps.planning.schemas import PlanningConstraints
from apps.planning.services import PlanningService
from apps.tasks.models import Task, TaskStatus
from common.time import to_utc


@dataclass(frozen=True, slots=True)
class CapacityForecast:
    range_start: datetime
    range_end: datetime
    total_schedulable_capacity_minutes: int
    remaining_free_minutes: int
    available_minutes: int
    committed_minutes: int
    unplanned_minutes: int
    risk: str
    reason_codes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "range_start": self.range_start,
            "range_end": self.range_end,
            "total_schedulable_capacity_minutes": self.total_schedulable_capacity_minutes,
            "remaining_free_minutes": self.remaining_free_minutes,
            # Compatibility alias: available_minutes means capacity remaining after commitments.
            "available_minutes": self.available_minutes,
            "committed_minutes": self.committed_minutes,
            "unplanned_minutes": self.unplanned_minutes,
            "risk": self.risk,
            "reason_codes": list(self.reason_codes),
        }


class CapacityForecastService:
    @staticmethod
    def forecast(
        *,
        user: User,
        range_start: datetime,
        range_end: datetime,
        slot_minutes: int = 30,
        allowed_weekdays: Sequence[int] | None = None,
    ) -> CapacityForecast:
        start = to_utc(range_start)
        end = to_utc(range_end)
        if end <= start:
            raise ValueError("range_end must be later than range_start")
        if slot_minutes < 5 or slot_minutes > 240:
            raise ValueError("slot_minutes must be between 5 and 240")
        base_constraints = PlanningConstraints(
            max_results=10000,
            slot_increment_minutes=slot_minutes,
            allowed_weekdays=(
                tuple(range(5)) if allowed_weekdays is None else tuple(allowed_weekdays)
            ),
        )
        total_slots = PlanningService.find_free_slots(
            user=user,
            range_start=start,
            range_end=end,
            duration_minutes=slot_minutes,
            constraints=replace(base_constraints, include_planned_tasks=False),
        )
        remaining_slots = PlanningService.find_free_slots(
            user=user,
            range_start=start,
            range_end=end,
            duration_minutes=slot_minutes,
            constraints=base_constraints,
        )
        total_capacity = len(total_slots) * slot_minutes
        remaining_capacity = len(remaining_slots) * slot_minutes
        committed = max(0, total_capacity - remaining_capacity)
        tasks = Task.objects.filter(
            user=user,
            status__in=[TaskStatus.PENDING, TaskStatus.IN_PROGRESS],
            due_at__isnull=False,
            due_at__gte=start,
            due_at__lte=end,
        )
        unplanned = sum(
            task.estimated_minutes or 30
            for task in tasks
            if (
                task.planned_start_at is None
                or task.planned_end_at is None
                or task.planned_start_at >= end
                or task.planned_end_at <= start
            )
        )
        reason_codes: list[str] = []
        if unplanned > remaining_capacity:
            risk = "over_capacity"
            reason_codes.append("unplanned_exceeds_free_capacity")
        elif unplanned > 0 and (remaining_capacity == 0 or unplanned >= remaining_capacity * 0.8):
            risk = "tight"
            reason_codes.append("unplanned_uses_most_free_capacity")
        else:
            risk = "within_capacity"
        if not tasks:
            reason_codes.append("no_due_tasks_in_range")
        return CapacityForecast(
            range_start=start,
            range_end=end,
            total_schedulable_capacity_minutes=total_capacity,
            remaining_free_minutes=remaining_capacity,
            available_minutes=remaining_capacity,
            committed_minutes=committed,
            unplanned_minutes=unplanned,
            risk=risk,
            reason_codes=tuple(reason_codes),
        )
