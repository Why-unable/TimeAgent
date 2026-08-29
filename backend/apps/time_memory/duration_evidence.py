from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from apps.tasks.models import Task, TaskExecutionSignal, TaskExecutionSignalType
from apps.time_memory.task_classification import classify_task


@dataclass(frozen=True, slots=True)
class DurationEvidence:
    task_id: str
    observed_at: datetime
    estimated_minutes: float
    actual_minutes: float
    segment: str
    semantic_segment: str


def explicit_task_segment(task: Task) -> str:
    """Return an auditable bucket, without pretending to classify task semantics."""
    if task.project.strip():
        return f"project:{task.project.strip().casefold()}"
    tags = task.tags if isinstance(task.tags, list) else []
    if tags:
        return f"tag:{str(tags[0]).strip().casefold()}"
    return "uncategorized"


def semantic_task_segment(task: Task) -> str:
    return classify_task(task).segment


def active_minutes(signals: list[TaskExecutionSignal]) -> float | None:
    open_started: datetime | None = None
    seconds = 0.0
    for signal in signals:
        if signal.signal_type in {
            TaskExecutionSignalType.STARTED,
            TaskExecutionSignalType.RESUMED,
        }:
            open_started = open_started or signal.occurred_at
        elif (
            signal.signal_type
            in {
                TaskExecutionSignalType.PAUSED,
                TaskExecutionSignalType.COMPLETED,
            }
            and open_started is not None
        ):
            seconds += max(0.0, (signal.occurred_at - open_started).total_seconds())
            open_started = None
    return seconds / 60 if seconds else None


def duration_evidence_for_tasks(tasks: list[Task]) -> list[DurationEvidence]:
    if not tasks:
        return []
    signals_by_task: dict[object, list[TaskExecutionSignal]] = {task.pk: [] for task in tasks}
    signals = TaskExecutionSignal.objects.filter(task_id__in=signals_by_task).order_by(
        "occurred_at", "created_at", "id"
    )
    for signal in signals:
        signals_by_task[signal.task_id].append(signal)
    rows: list[DurationEvidence] = []
    for task in tasks:
        if task.estimated_minutes is None:
            continue
        actual = active_minutes(signals_by_task[task.pk])
        if actual is None or actual <= 0:
            continue
        rows.append(
            DurationEvidence(
                task_id=str(task.pk),
                observed_at=task.completed_at or signals_by_task[task.pk][-1].occurred_at,
                estimated_minutes=float(task.estimated_minutes),
                actual_minutes=actual,
                segment=explicit_task_segment(task),
                semantic_segment=semantic_task_segment(task),
            )
        )
    return rows
