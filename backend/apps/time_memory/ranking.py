from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from apps.time_memory.schemas import StablePattern, TimeMemoryProfile, WindowName

type MemoryIntent = Literal[
    "current_load",
    "long_term_habit",
    "planning_style",
    "schedule_changes",
    "location",
    "general_planning",
    "none",
]

INTENT_KEYWORDS: tuple[tuple[MemoryIntent, tuple[str, ...]], ...] = (
    ("current_load", ("忙", "负荷", "空闲", "最近", "累", "load")),
    ("long_term_habit", ("长期", "一直", "通常", "习惯", "一般", "habit")),
    ("planning_style", ("怎么计划", "规划方式", "批量", "提前", "planning style")),
    ("schedule_changes", ("延期", "推迟", "改期", "取消", "调整", "reschedule")),
    ("location", ("地点", "哪里", "会议室", "地址", "location", "place")),
    ("general_planning", ("安排", "计划", "规划", "日程", "schedule", "plan")),
)

WINDOW_ORDER: dict[MemoryIntent, tuple[WindowName, ...]] = {
    "current_load": ("7d", "30d", "180d"),
    "long_term_habit": ("180d", "30d", "7d"),
    "planning_style": ("30d", "180d", "7d"),
    "schedule_changes": ("30d", "7d", "180d"),
    "location": ("30d", "180d", "7d"),
    "general_planning": ("7d", "30d", "180d"),
    "none": (),
}


@dataclass(frozen=True, slots=True)
class MemoryContextCandidate:
    candidate_id: str
    category: str
    text: str
    score: float
    token_count: int = 0


def classify_memory_intent(text: str) -> MemoryIntent:
    normalized = text.casefold()
    for intent, keywords in INTENT_KEYWORDS:
        if any(keyword in normalized for keyword in keywords):
            return intent
    return "none"


def _pattern_relevance(pattern: StablePattern, intent: MemoryIntent) -> float:
    expected = {
        "current_load": "schedule",
        "planning_style": "planning",
        "schedule_changes": "change",
        "location": "place",
        "general_planning": "schedule",
    }.get(intent)
    if intent == "long_term_habit":
        return 1.0
    return 1.0 if pattern.pattern_type == expected else 0.6 if intent == "general_planning" else 0


def rank_patterns(
    profile: TimeMemoryProfile,
    intent: MemoryIntent,
    *,
    now: datetime,
) -> list[StablePattern]:
    ranked: list[tuple[float, StablePattern]] = []
    for pattern in profile.stable_patterns:
        if pattern.status != "active" or pattern.confidence < 0.7:
            continue
        relevance = _pattern_relevance(pattern, intent)
        if relevance == 0:
            continue
        age = (now - pattern.last_confirmed_at).days
        recency = 1.0 if age <= 7 else 0.8 if age <= 30 else 0.5 if age <= 90 else 0.2
        evidence_set = set(pattern.evidence_windows)
        evidence = (
            1.0
            if {"30d", "180d"}.issubset(evidence_set)
            else 0.7
            if "180d" in evidence_set
            else 0.6
            if "30d" in evidence_set
            else 0.3
            if "7d" in evidence_set
            else 0
        )
        score = 0.4 * relevance + 0.25 * pattern.confidence + 0.2 * recency + 0.15 * evidence
        ranked.append((score, pattern.model_copy(update={"score": score})))
    return [pattern for _, pattern in sorted(ranked, key=lambda item: item[0], reverse=True)[:5]]


def collect_candidates(
    profile: TimeMemoryProfile,
    intent: MemoryIntent,
    *,
    now: datetime | None = None,
) -> list[MemoryContextCandidate]:
    if intent == "none":
        return []
    candidates: list[MemoryContextCandidate] = []
    for index, window_name in enumerate(WINDOW_ORDER[intent]):
        window = profile.behavior_windows[window_name]
        if window.confidence < 0.55:
            continue
        parts: list[str] = []
        if intent in {"current_load", "general_planning", "location"}:
            parts.append(window.schedule_pattern.summary)
        if intent in {"planning_style", "general_planning", "long_term_habit"}:
            parts.append(window.planning_pattern.summary)
        if intent in {"schedule_changes", "long_term_habit"}:
            parts.append(window.change_pattern.summary)
        text = " ".join(part for part in parts if part)
        if text:
            candidates.append(
                MemoryContextCandidate(
                    candidate_id=f"window.{window_name}",
                    category="window",
                    text=f"{window_name}：{text}",
                    score=(1.0 if intent == "long_term_habit" else 1.2) - index * 0.1,
                )
            )
    if intent == "location":
        ordered_places = sorted(
            profile.common_places,
            key=lambda place: (
                place.score,
                place.last_seen_at or profile.generated_at,
                place.event_count,
                place.total_scheduled_hours,
                place.confidence,
            ),
            reverse=True,
        )
        for index, place in enumerate(ordered_places[:5]):
            candidates.append(
                MemoryContextCandidate(
                    candidate_id=f"place.{place.place_id}",
                    category="place",
                    text=f"常用地点“{place.name}”：近 180 天出现 {place.event_count} 次。",
                    score=1.3 - index * 0.05,
                )
            )
    for pattern in rank_patterns(profile, intent, now=now or profile.generated_at):
        score = pattern.score + (0.4 if intent == "long_term_habit" else 0)
        candidates.append(
            MemoryContextCandidate(
                candidate_id=f"pattern.{pattern.pattern_id}",
                category="stable_pattern",
                text=pattern.summary,
                score=score,
            )
        )
    return sorted(candidates, key=lambda item: item.score, reverse=True)
