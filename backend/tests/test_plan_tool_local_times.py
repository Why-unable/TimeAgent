from typing import Any

import pytest

from apps.agents.tools.planning_tools import _plan_items_with_local_times


def test_plan_tool_items_include_user_local_times_across_utc_date_boundary() -> None:
    items: list[dict[str, Any]] = [
        {
            "kind": "scheduled_task",
            "start_at": "2026-10-07T17:30:00+00:00",
            "end_at": "2026-10-07T18:30:00+00:00",
        }
    ]

    result = _plan_items_with_local_times(items, timezone="Asia/Shanghai")

    assert result[0]["start_at"] == "2026-10-07T17:30:00+00:00"
    assert result[0]["end_at"] == "2026-10-07T18:30:00+00:00"
    assert result[0]["start_at_local"] == "2026-10-08T01:30:00+08:00"
    assert result[0]["end_at_local"] == "2026-10-08T02:30:00+08:00"
    assert "start_at_local" not in items[0]


def test_plan_tool_items_reject_naive_schedule_timestamps() -> None:
    items: list[dict[str, Any]] = [{"kind": "scheduled_task", "start_at": "2026-10-07T17:30:00"}]
    with pytest.raises(ValueError, match="must include a timezone"):
        _plan_items_with_local_times(items, timezone="Asia/Shanghai")
