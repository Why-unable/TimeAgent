from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class ScheduledItem:
    task_id: str
    start_at: datetime
    end_at: datetime
    due_at: datetime


def run_adaptive_stability_benchmark() -> dict[str, object]:
    """Compare bounded repair with a deterministic full-compaction baseline."""
    day = datetime(2026, 8, 24, tzinfo=UTC)
    original = (
        _item("affected", day.replace(hour=9), day.replace(hour=10), day.replace(hour=18)),
        _item("stable-a", day.replace(hour=13), day.replace(hour=14), day.replace(hour=18)),
        _item("stable-b", day.replace(hour=17), day.replace(hour=18), day.replace(hour=19)),
    )
    local = (
        _item("affected", day.replace(hour=10), day.replace(hour=11), day.replace(hour=18)),
        original[1],
        original[2],
    )
    full = (
        _item("affected", day.replace(hour=10), day.replace(hour=11), day.replace(hour=18)),
        _item("stable-a", day.replace(hour=11), day.replace(hour=12), day.replace(hour=18)),
        _item("stable-b", day.replace(hour=12), day.replace(hour=13), day.replace(hour=19)),
    )
    return {
        "benchmark": "adaptive-stability-v1",
        "case_count": 1,
        "blocked_interval": {
            "start_at": day.replace(hour=9).isoformat(),
            "end_at": day.replace(hour=10).isoformat(),
        },
        "bounded_local_replan": _metrics(original, local),
        "full_compaction_baseline": _metrics(original, full),
        "claim": "synthetic_stability_comparison_not_product_outcome",
    }


def _item(task_id: str, start_at: datetime, end_at: datetime, due_at: datetime) -> ScheduledItem:
    return ScheduledItem(task_id, start_at, end_at, due_at)


def _metrics(
    original: tuple[ScheduledItem, ...], candidate: tuple[ScheduledItem, ...]
) -> dict[str, int]:
    original_by_id = {item.task_id: item for item in original}
    movement = [
        int(abs((item.start_at - original_by_id[item.task_id].start_at).total_seconds()) // 60)
        for item in candidate
    ]
    return {
        "moved_count": sum(1 for minutes in movement if minutes > 0),
        "total_move_minutes": sum(movement),
        "max_move_minutes": max(movement, default=0),
        "deadline_violations": sum(1 for item in candidate if item.end_at > item.due_at),
        "overlap_violations": sum(
            1
            for index, item in enumerate(candidate)
            for other in candidate[index + 1 :]
            if item.start_at < other.end_at and item.end_at > other.start_at
        ),
    }
