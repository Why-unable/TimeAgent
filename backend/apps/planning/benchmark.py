"""Small, deterministic planning benchmark primitives.

The benchmark intentionally models the current proposal baseline: tasks are consumed in
the supplied order and each task takes the first remaining slot that can fit it. It is
not an optimizer and must remain stable while a better planner is developed.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True, slots=True)
class BenchmarkTask:
    task_id: str
    duration_minutes: int


@dataclass(frozen=True, slots=True)
class BenchmarkSlot:
    start_at: datetime
    end_at: datetime

    @property
    def duration_minutes(self) -> int:
        return int((self.end_at - self.start_at).total_seconds() // 60)


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    name: str
    tasks: tuple[BenchmarkTask, ...]
    slots: tuple[BenchmarkSlot, ...]


@dataclass(frozen=True, slots=True)
class BenchmarkCaseResult:
    name: str
    task_count: int
    scheduled_count: int
    scheduled_minutes: int
    unscheduled_task_ids: tuple[str, ...]
    hard_constraint_violations: int

    @property
    def placement_ratio(self) -> float:
        if self.task_count == 0:
            return 1.0
        return self.scheduled_count / self.task_count


def run_baseline(case: BenchmarkCase) -> BenchmarkCaseResult:
    remaining_slots = list(case.slots)
    scheduled_count = 0
    scheduled_minutes = 0
    unscheduled: list[str] = []
    placements: list[tuple[datetime, datetime]] = []
    for task in case.tasks:
        selected_index = next(
            (
                index
                for index, slot in enumerate(remaining_slots)
                if slot.duration_minutes >= task.duration_minutes
            ),
            None,
        )
        if selected_index is None:
            unscheduled.append(task.task_id)
            continue
        selected = remaining_slots.pop(selected_index)
        scheduled_count += 1
        scheduled_minutes += task.duration_minutes
        consumed_end = selected.start_at + timedelta(minutes=task.duration_minutes)
        placements.append((selected.start_at, consumed_end))
        if consumed_end < selected.end_at:
            remaining_slots.insert(
                selected_index,
                BenchmarkSlot(start_at=consumed_end, end_at=selected.end_at),
            )
    return BenchmarkCaseResult(
        name=case.name,
        task_count=len(case.tasks),
        scheduled_count=scheduled_count,
        scheduled_minutes=scheduled_minutes,
        unscheduled_task_ids=tuple(unscheduled),
        hard_constraint_violations=_overlap_count(placements),
    )


def run_v2_candidate(case: BenchmarkCase) -> BenchmarkCaseResult:
    """Deterministic comparison candidate: longest tasks first, best-fit slot."""
    ordered = tuple(sorted(case.tasks, key=lambda task: (-task.duration_minutes, task.task_id)))
    remaining_slots = list(case.slots)
    scheduled: list[str] = []
    scheduled_minutes = 0
    placements: list[tuple[datetime, datetime]] = []
    for task in ordered:
        candidates = [
            (index, slot)
            for index, slot in enumerate(remaining_slots)
            if slot.duration_minutes >= task.duration_minutes
        ]
        if not candidates:
            continue
        selected_index, selected = min(
            candidates, key=lambda pair: (pair[1].duration_minutes - task.duration_minutes, pair[0])
        )
        remaining_slots.pop(selected_index)
        consumed_end = selected.start_at + timedelta(minutes=task.duration_minutes)
        placements.append((selected.start_at, consumed_end))
        if consumed_end < selected.end_at:
            remaining_slots.insert(
                selected_index,
                BenchmarkSlot(start_at=consumed_end, end_at=selected.end_at),
            )
        scheduled.append(task.task_id)
        scheduled_minutes += task.duration_minutes
    scheduled_ids = set(scheduled)
    return BenchmarkCaseResult(
        name=case.name,
        task_count=len(case.tasks),
        scheduled_count=len(scheduled),
        scheduled_minutes=scheduled_minutes,
        unscheduled_task_ids=tuple(
            task.task_id for task in case.tasks if task.task_id not in scheduled_ids
        ),
        hard_constraint_violations=_overlap_count(placements),
    )


def default_cases() -> tuple[BenchmarkCase, ...]:
    start = datetime(2026, 8, 24, 1, 0, tzinfo=UTC)
    return (
        BenchmarkCase(
            name="ordered_fit",
            tasks=(
                BenchmarkTask("task-a", 30),
                BenchmarkTask("task-b", 45),
                BenchmarkTask("task-c", 60),
            ),
            slots=(BenchmarkSlot(start, start + timedelta(hours=3)),),
        ),
        BenchmarkCase(
            name="fragmented_capacity",
            tasks=(
                BenchmarkTask("task-a", 60),
                BenchmarkTask("task-b", 45),
                BenchmarkTask("task-c", 30),
            ),
            slots=(
                BenchmarkSlot(start, start + timedelta(minutes=60)),
                BenchmarkSlot(start + timedelta(hours=2), start + timedelta(hours=3)),
            ),
        ),
        BenchmarkCase(
            name="oversubscribed",
            tasks=(
                BenchmarkTask("task-a", 90),
                BenchmarkTask("task-b", 60),
                BenchmarkTask("task-c", 45),
            ),
            slots=(BenchmarkSlot(start, start + timedelta(hours=2)),),
        ),
        BenchmarkCase(
            name="best_fit_advantage",
            tasks=(
                BenchmarkTask("task-a", 60),
                BenchmarkTask("task-b", 90),
            ),
            slots=(
                BenchmarkSlot(start, start + timedelta(minutes=90)),
                BenchmarkSlot(start + timedelta(hours=2), start + timedelta(hours=3)),
            ),
        ),
    )


def run_default_benchmark() -> dict[str, object]:
    results = [run_baseline(case) for case in default_cases()]
    candidate_results = [run_v2_candidate(case) for case in default_cases()]
    task_count = sum(result.task_count for result in results)
    scheduled_count = sum(result.scheduled_count for result in results)
    return {
        "benchmark": "planning-baseline-v1",
        "algorithm": "first-fit-in-input-order",
        "case_count": len(results),
        "task_count": task_count,
        "scheduled_count": scheduled_count,
        "placement_ratio": scheduled_count / task_count if task_count else 1.0,
        "cases": [
            {
                "name": result.name,
                "task_count": result.task_count,
                "scheduled_count": result.scheduled_count,
                "scheduled_minutes": result.scheduled_minutes,
                "placement_ratio": result.placement_ratio,
                "unscheduled_task_ids": list(result.unscheduled_task_ids),
                "hard_constraint_violations": result.hard_constraint_violations,
            }
            for result in results
        ],
        "comparison": {
            "algorithm": "longest-first-best-fit-candidate",
            "scheduled_count": sum(result.scheduled_count for result in candidate_results),
            "scheduled_minutes": sum(result.scheduled_minutes for result in candidate_results),
            "placement_ratio": (
                sum(result.scheduled_count for result in candidate_results) / task_count
                if task_count
                else 1.0
            ),
            "hard_constraint_violations": sum(
                result.hard_constraint_violations for result in candidate_results
            ),
            "cases": [
                {
                    "name": result.name,
                    "scheduled_count": result.scheduled_count,
                    "scheduled_minutes": result.scheduled_minutes,
                    "unscheduled_task_ids": list(result.unscheduled_task_ids),
                    "hard_constraint_violations": result.hard_constraint_violations,
                }
                for result in candidate_results
            ],
        },
    }


def _overlap_count(placements: list[tuple[datetime, datetime]]) -> int:
    return sum(
        1
        for index, (start_at, end_at) in enumerate(placements)
        for other_start, other_end in placements[index + 1 :]
        if start_at < other_end and end_at > other_start
    )
