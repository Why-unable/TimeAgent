from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True, slots=True)
class TimeMemorySettings:
    schema_version: int = 2
    history_days: int = 180
    window_days: tuple[int, ...] = (7, 30, 180)
    planning_session_gap_minutes: int = 15
    batch_planning_minimum: int = 3
    common_place_limit: int = 8
    min_place_event_count: int = 3
    place_weak_after_days: int = 90
    busy_day_hours: float = 8.0
    light_day_hours: float = 3.0
    rest_day_hours: float = 1.0
    stable_pattern_expire_rebuilds: int = 3
    stable_pattern_min_confidence: float = 0.70
    min_injection_confidence: float = 0.55
    prompt_token_budget: int = 800
    refresh_delay_seconds: int = 5
    auto_refresh_enabled: bool = True


def get_time_memory_settings() -> TimeMemorySettings:
    return TimeMemorySettings(
        prompt_token_budget=int(getattr(settings, "TIME_MEMORY_PROMPT_TOKEN_BUDGET", 800)),
        refresh_delay_seconds=int(getattr(settings, "TIME_MEMORY_REFRESH_DELAY_SECONDS", 5)),
        auto_refresh_enabled=bool(getattr(settings, "TIME_MEMORY_AUTO_REFRESH_ENABLED", True)),
    )
