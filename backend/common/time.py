from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class InvalidTimezoneError(ValueError):
    pass


class NaiveDateTimeError(ValueError):
    pass


class AmbiguousLocalTimeError(ValueError):
    pass


class NonexistentLocalTimeError(ValueError):
    pass


def get_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise InvalidTimezoneError(f"Unknown IANA timezone: {timezone_name}") from exc


def validate_timezone(timezone_name: str) -> None:
    get_timezone(timezone_name)


def to_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise NaiveDateTimeError("A timezone-aware datetime is required")
    return value.astimezone(UTC)


def to_user_timezone(value: datetime, timezone_name: str) -> datetime:
    return to_utc(value).astimezone(get_timezone(timezone_name))


def now_in_timezone(current_datetime: datetime, timezone_name: str) -> datetime:
    return to_user_timezone(current_datetime, timezone_name)


def resolve_local_datetime(
    local_datetime: datetime,
    timezone_name: str,
    *,
    fold: int | None = None,
) -> datetime:
    if local_datetime.tzinfo is not None:
        raise ValueError("local_datetime must be naive")
    if fold not in (None, 0, 1):
        raise ValueError("fold must be 0, 1, or None")

    timezone = get_timezone(timezone_name)
    valid_candidates: dict[int, datetime] = {}

    for candidate_fold in (0, 1):
        candidate = local_datetime.replace(tzinfo=timezone, fold=candidate_fold)
        round_trip = candidate.astimezone(UTC).astimezone(timezone)
        if round_trip.replace(tzinfo=None) == local_datetime:
            valid_candidates[candidate_fold] = candidate

    if not valid_candidates:
        raise NonexistentLocalTimeError(
            f"{local_datetime.isoformat()} does not exist in {timezone_name}"
        )

    offsets = {candidate.utcoffset() for candidate in valid_candidates.values()}
    if len(offsets) > 1:
        if fold is None:
            raise AmbiguousLocalTimeError(
                f"{local_datetime.isoformat()} is ambiguous in {timezone_name}; provide fold"
            )
        return valid_candidates[fold].astimezone(UTC)

    return next(iter(valid_candidates.values())).astimezone(UTC)

