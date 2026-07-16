from datetime import UTC, datetime

import pytest

from common.time import (
    AmbiguousLocalTimeError,
    InvalidTimezoneError,
    NaiveDateTimeError,
    NonexistentLocalTimeError,
    get_timezone,
    now_in_timezone,
    resolve_local_datetime,
    to_user_timezone,
    to_utc,
    validate_timezone,
)


def test_converts_aware_datetime_to_utc_and_user_timezone() -> None:
    shanghai_time = datetime(2026, 7, 17, 15, 0, tzinfo=get_timezone("Asia/Shanghai"))

    assert to_utc(shanghai_time) == datetime(2026, 7, 17, 7, 0, tzinfo=UTC)
    assert to_user_timezone(
        datetime(2026, 7, 17, 7, 0, tzinfo=UTC), "Asia/Shanghai"
    ).hour == 15


def test_rejects_naive_datetime_and_invalid_timezone() -> None:
    with pytest.raises(NaiveDateTimeError):
        to_utc(datetime(2026, 7, 17, 7, 0))

    with pytest.raises(InvalidTimezoneError):
        validate_timezone("UTC+8")


def test_resolves_unambiguous_local_datetime_to_utc() -> None:
    resolved = resolve_local_datetime(
        datetime(2026, 7, 17, 15, 0),
        "Asia/Shanghai",
    )

    assert resolved == datetime(2026, 7, 17, 7, 0, tzinfo=UTC)


def test_requires_fold_for_ambiguous_daylight_saving_time() -> None:
    local_time = datetime(2026, 11, 1, 1, 30)

    with pytest.raises(AmbiguousLocalTimeError):
        resolve_local_datetime(local_time, "America/New_York")

    assert resolve_local_datetime(
        local_time, "America/New_York", fold=0
    ) == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert resolve_local_datetime(
        local_time, "America/New_York", fold=1
    ) == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)


def test_rejects_nonexistent_daylight_saving_time() -> None:
    with pytest.raises(NonexistentLocalTimeError):
        resolve_local_datetime(
            datetime(2026, 3, 8, 2, 30),
            "America/New_York",
        )


def test_current_time_is_explicitly_injected() -> None:
    current_datetime = datetime(2026, 7, 15, 2, 0, tzinfo=UTC)

    result = now_in_timezone(current_datetime, "Asia/Shanghai")

    assert result == datetime(
        2026,
        7,
        15,
        10,
        0,
        tzinfo=result.tzinfo,
    )
