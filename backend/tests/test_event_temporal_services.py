from datetime import UTC, datetime, time

import pytest
from pydantic import ValidationError

from apps.events.temporal_services import (
    AbsoluteEventTime,
    EventTemporalResolutionService,
    RelativeEventTime,
)
from common.time import NonexistentLocalTimeError


def test_relative_day_uses_the_new_run_anchor_in_user_timezone() -> None:
    resolution = EventTemporalResolutionService.resolve(
        anchor_at=datetime(2026, 8, 12, 2, tzinfo=UTC),
        timezone="Asia/Shanghai",
        specification=RelativeEventTime(
            kind="relative",
            offset=2,
            unit="day",
            source_text="两天后",
            duration_minutes=60,
        ),
    )

    assert resolution.start_at == datetime(2026, 8, 14, 2, tzinfo=UTC)
    assert resolution.end_at == datetime(2026, 8, 14, 3, tzinfo=UTC)
    assert resolution.as_audit_payload()["anchor_at"] == "2026-08-12T02:00:00+00:00"


def test_calendar_day_preserves_wall_clock_across_dst() -> None:
    resolution = EventTemporalResolutionService.resolve(
        anchor_at=datetime(2026, 3, 7, 17, tzinfo=UTC),
        timezone="America/New_York",
        specification=RelativeEventTime(
            kind="relative",
            offset=1,
            unit="day",
            source_text="tomorrow",
            duration_minutes=30,
        ),
    )

    assert resolution.start_at == datetime(2026, 3, 8, 16, tzinfo=UTC)


def test_nonexistent_requested_local_time_is_rejected() -> None:
    with pytest.raises(NonexistentLocalTimeError):
        EventTemporalResolutionService.resolve(
            anchor_at=datetime(2026, 3, 7, 17, tzinfo=UTC),
            timezone="America/New_York",
            specification=RelativeEventTime(
                kind="relative",
                offset=1,
                unit="day",
                source_text="tomorrow at 2:30",
                local_time=time(2, 30),
                duration_minutes=30,
            ),
        )


def test_absolute_variant_normalizes_one_interval() -> None:
    resolution = EventTemporalResolutionService.resolve(
        anchor_at=datetime(2026, 8, 12, 2, tzinfo=UTC),
        timezone="Asia/Shanghai",
        specification=AbsoluteEventTime(
            kind="absolute",
            start_at=datetime.fromisoformat("2026-08-20T15:00:00+08:00"),
            end_at=datetime.fromisoformat("2026-08-20T16:00:00+08:00"),
        ),
    )

    assert resolution.start_at == datetime(2026, 8, 20, 7, tzinfo=UTC)
    assert resolution.end_at == datetime(2026, 8, 20, 8, tzinfo=UTC)


def test_union_rejects_mixed_or_missing_variants_without_inspecting_prose() -> None:
    with pytest.raises(ValidationError):
        EventTemporalResolutionService.parse(
            {
                "kind": "relative",
                "offset": 2,
                "unit": "day",
                "source_text": "两天后",
                "duration_minutes": 60,
                "start_at": "2026-08-14T10:00:00+08:00",
            }
        )
    with pytest.raises(ValidationError):
        EventTemporalResolutionService.parse(
            {
                "start_at": "2026-08-14T10:00:00+08:00",
                "end_at": "2026-08-14T11:00:00+08:00",
            }
        )
