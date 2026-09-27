from datetime import UTC, datetime
from types import SimpleNamespace

from apps.agents.tools.common import model_dict


def test_model_dict_adds_user_timezone_display_values_without_changing_utc_facts() -> None:
    due_at = datetime(2026, 10, 12, 1, 0, tzinfo=UTC)
    record = SimpleNamespace(due_at=due_at, title="Review")

    result = model_dict(
        record,
        ("title", "due_at"),
        display_timezone="Asia/Shanghai",
    )

    assert result["due_at"] == "2026-10-12T01:00:00+00:00"
    assert result["due_at_local"] == "2026-10-12T09:00:00+08:00"
    assert result["display_timezone"] == "Asia/Shanghai"
