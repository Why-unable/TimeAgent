from datetime import UTC, datetime

import pytest

from common.temporal_context import TemporalContextSnapshot


def test_temporal_context_snapshot_uses_explicit_timezone_and_utc_bounds() -> None:
    snapshot = TemporalContextSnapshot.build(
        now=datetime(2026, 8, 23, 16, 30, tzinfo=UTC),
        timezone_name="Asia/Shanghai",
    )

    assert snapshot.now_utc == datetime(2026, 8, 23, 16, 30, tzinfo=UTC)
    assert snapshot.local_date.isoformat() == "2026-08-24"
    assert snapshot.day_start_utc == datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
    assert snapshot.day_end_utc == datetime(2026, 8, 24, 16, 0, tzinfo=UTC)


def test_temporal_context_snapshot_rejects_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone"):
        TemporalContextSnapshot.build(
            now=datetime(2026, 8, 24, 0, 0),
            timezone_name="Asia/Shanghai",
        )
