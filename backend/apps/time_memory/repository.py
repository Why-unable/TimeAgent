from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langgraph.store.base import BaseStore
from pydantic import ValidationError

from apps.time_memory.schemas import TimeMemoryProfile

PROFILE_KEY = "profile"


def _number(value: object) -> float:
    return float(value) if isinstance(value, int | float) else 0


def _integer(value: object) -> int:
    return int(value) if isinstance(value, int) else 0


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _migrate_v1_to_v2(document: dict[str, object]) -> dict[str, object]:
    migrated = dict(document)
    timezone_name = str(document.get("timezone") or "UTC")
    data_until = datetime.fromisoformat(str(document["data_until"]).replace("Z", "+00:00"))
    end_date = data_until.astimezone(ZoneInfo(timezone_name)).date()
    old_windows = _mapping(document.get("behavior_windows"))
    windows: dict[str, object] = {}
    for window_name, days in (("7d", 7), ("30d", 30), ("180d", 180)):
        old = _mapping(old_windows.get(window_name))
        event_count = _integer(old.get("event_count"))
        scheduled_minutes = _number(old.get("scheduled_minutes"))
        sessions = _integer(old.get("planning_session_count"))
        batch_ratio = min(1.0, max(0.0, _number(old.get("batch_planning_ratio"))))
        rescheduled = _integer(old.get("reschedule_count"))
        cancelled = _integer(old.get("cancellation_count"))
        change_denominator = max(event_count + cancelled, 1)
        planning_style = (
            "insufficient_data"
            if sessions == 0
            else "batch"
            if batch_ratio >= 0.6
            else "incremental"
            if batch_ratio <= 0.25
            else "mixed"
        )
        windows[window_name] = {
            "window": window_name,
            "start_date": end_date - timedelta(days=days - 1),
            "end_date": end_date,
            "sample_days": days,
            "event_count": event_count,
            "task_count": _integer(old.get("task_count")),
            "completed_task_count": _integer(old.get("completed_task_count")),
            "cancelled_task_count": _integer(old.get("cancelled_task_count")),
            "source_distribution": _mapping(old.get("source_distribution")),
            "schedule_pattern": {
                "total_scheduled_hours": scheduled_minutes / 60,
                "average_daily_scheduled_hours": _number(old.get("average_daily_scheduled_minutes"))
                / 60,
                "scheduled_day_count": _integer(old.get("active_days")),
                "peak_time_ranges": [
                    f"{hour:02d}:00-{(hour + 1) % 24:02d}:00"
                    for hour in _list(old.get("preferred_start_hours"))
                    if isinstance(hour, int) and 0 <= hour <= 23
                ],
                "summary": str(old.get("summary") or ""),
            },
            "planning_pattern": {
                "creation_session_count": sessions,
                "batch_creation_ratio": batch_ratio,
                "incremental_creation_ratio": 1 - batch_ratio if sessions else 0,
                "planning_style": planning_style,
                "summary": (
                    "旧版画像显示用户倾向于批量规划。"
                    if planning_style == "batch"
                    else "旧版画像显示用户倾向于逐步添加安排。"
                    if planning_style == "incremental"
                    else "旧版画像显示用户同时采用批量和逐步规划。"
                    if planning_style == "mixed"
                    else "旧版画像没有足够的规划样本。"
                ),
            },
            "change_pattern": {
                "modified_event_count": rescheduled,
                "rescheduled_event_count": rescheduled,
                "cancelled_event_count": cancelled,
                "reschedule_ratio": rescheduled / change_denominator,
                "cancellation_ratio": cancelled / change_denominator,
                "summary": "旧版画像记录了日程调整统计，等待下一次完整重建校正。",
            },
            "summary": str(old.get("summary") or ""),
            "confidence": min(1.0, max(0.0, _number(old.get("confidence")))),
        }
    places = []
    for raw_place in _list(document.get("common_places")):
        if not isinstance(raw_place, dict) or not str(raw_place.get("name") or "").strip():
            continue
        name = str(raw_place["name"]).strip()
        normalized = " ".join(name.casefold().split())
        count = max(1, _integer(raw_place.get("event_count")))
        places.append(
            {
                "place_id": normalized.replace(" ", "_")[:80],
                "name": name,
                "normalized_name": normalized,
                "event_count": count,
                "last_seen_at": raw_place.get("last_seen_at"),
                "confidence": min(1.0, count / 10),
                "score": min(1.0, count / 10),
            }
        )
    patterns = []
    for raw_pattern in _list(document.get("stable_patterns")):
        if not isinstance(raw_pattern, dict):
            continue
        evidence_count = _integer(raw_pattern.get("evidence_count"))
        patterns.append(
            {
                "pattern_id": raw_pattern.get("key"),
                "pattern_type": raw_pattern.get("category"),
                "summary": raw_pattern.get("summary", ""),
                "evidence_windows": (
                    ["30d", "180d"]
                    if evidence_count >= 2
                    else ["180d"]
                    if evidence_count == 1
                    else []
                ),
                "confidence": raw_pattern.get("confidence", 0),
                "first_detected_at": raw_pattern.get("first_seen_at"),
                "last_confirmed_at": raw_pattern.get("last_confirmed_at"),
            }
        )
    migrated.update(
        schema_version=2,
        common_places=places,
        behavior_windows=windows,
        stable_patterns=patterns,
    )
    return migrated


def migrate_profile(document: dict[str, object]) -> TimeMemoryProfile | None:
    """Migrate known Store documents; invalid profiles are rebuilt from business facts."""

    schema_version = document.get("schema_version", 1)
    if schema_version == 1:
        try:
            document = _migrate_v1_to_v2(document)
        except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError):
            return None
    elif schema_version != 2:
        return None
    try:
        return TimeMemoryProfile.model_validate(document)
    except ValidationError:
        return None


class TimeMemoryRepository:
    @staticmethod
    def namespace(user_id: str) -> tuple[str, str, str]:
        return ("users", user_id, "time_memory")

    @classmethod
    def get(cls, store: BaseStore, *, user_id: str) -> TimeMemoryProfile | None:
        item = store.get(cls.namespace(user_id), PROFILE_KEY)
        if item is None:
            return None
        if not isinstance(item.value, dict):
            return None
        return migrate_profile(item.value)

    @classmethod
    async def aget(cls, store: BaseStore, *, user_id: str) -> TimeMemoryProfile | None:
        item = await store.aget(cls.namespace(user_id), PROFILE_KEY)
        if item is None or not isinstance(item.value, dict):
            return None
        return migrate_profile(item.value)

    @classmethod
    def put(cls, store: BaseStore, profile: TimeMemoryProfile) -> None:
        store.put(
            cls.namespace(profile.user_id),
            PROFILE_KEY,
            profile.model_dump(mode="json"),
        )

    @classmethod
    async def aput(cls, store: BaseStore, profile: TimeMemoryProfile) -> None:
        await store.aput(
            cls.namespace(profile.user_id),
            PROFILE_KEY,
            profile.model_dump(mode="json"),
        )

    @classmethod
    def delete(cls, store: BaseStore, *, user_id: str) -> None:
        store.delete(cls.namespace(user_id), PROFILE_KEY)

    @classmethod
    async def adelete(cls, store: BaseStore, *, user_id: str) -> None:
        await store.adelete(cls.namespace(user_id), PROFILE_KEY)
