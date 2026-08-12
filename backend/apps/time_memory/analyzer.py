from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from statistics import median
from typing import Literal, cast
from zoneinfo import ZoneInfo

from apps.events.models import CalendarEvent, CalendarEventStatus
from apps.time_memory.models import MemoryEntityType, MemoryOperation, ScheduleChange
from apps.time_memory.schemas import (
    BehaviorWindow,
    ChangePattern,
    CommonPlace,
    PlanningPattern,
    SchedulePattern,
    StablePattern,
    TimeMemoryProfile,
    WindowName,
)
from apps.time_memory.settings import TimeMemorySettings
from apps.time_memory.source_repository import TimeMemorySourceData


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _window_bounds(now: datetime, timezone_name: str, days: int) -> tuple[date, date, datetime]:
    timezone = ZoneInfo(timezone_name)
    end_date = now.astimezone(timezone).date()
    start_date = end_date - timedelta(days=days - 1)
    start_at = datetime.combine(start_date, time.min, tzinfo=timezone).astimezone(UTC)
    return start_date, end_date, start_at


def _daily_union_minutes(
    events: list[CalendarEvent], *, start: datetime, end: datetime, timezone_name: str
) -> tuple[dict[date, int], Counter[int], Counter[int]]:
    timezone = ZoneInfo(timezone_name)
    intervals: dict[date, list[tuple[datetime, datetime]]] = {}
    hour_minutes: Counter[int] = Counter()
    for event in events:
        cursor = max(event.start_at, start).astimezone(timezone)
        local_end = min(event.end_at, end).astimezone(timezone)
        while cursor < local_end:
            next_day = datetime.combine(
                cursor.date() + timedelta(days=1), time.min, tzinfo=timezone
            )
            segment_end = min(local_end, next_day)
            intervals.setdefault(cursor.date(), []).append((cursor, segment_end))
            hour_cursor = cursor
            while hour_cursor < segment_end:
                next_hour = min(
                    segment_end,
                    hour_cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1),
                )
                hour_minutes[hour_cursor.hour] += int(
                    (next_hour - hour_cursor).total_seconds() // 60
                )
                hour_cursor = next_hour
            cursor = segment_end
    daily: dict[date, int] = {}
    weekdays: Counter[int] = Counter()
    for day, values in intervals.items():
        merged: list[list[datetime]] = []
        for interval_start, interval_end in sorted(values):
            if not merged or interval_start > merged[-1][1]:
                merged.append([interval_start, interval_end])
            else:
                merged[-1][1] = max(merged[-1][1], interval_end)
        daily[day] = sum(
            int((interval_end - interval_start).total_seconds() // 60)
            for interval_start, interval_end in merged
        )
        weekdays[day.weekday()] += daily[day]
    return daily, weekdays, hour_minutes


def _creation_sessions(
    changes: list[ScheduleChange], gap_minutes: int
) -> list[list[ScheduleChange]]:
    sessions: list[list[ScheduleChange]] = []
    for change in sorted(changes, key=lambda item: item.occurred_at):
        if not sessions or change.occurred_at - sessions[-1][-1].occurred_at > timedelta(
            minutes=gap_minutes
        ):
            sessions.append([change])
        else:
            sessions[-1].append(change)
    return sessions


class TimeMemoryAnalyzer:
    def __init__(self, config: TimeMemorySettings) -> None:
        self.config = config

    def build_profile(
        self,
        *,
        user_id: str,
        timezone_name: str,
        now: datetime,
        source: TimeMemorySourceData,
        previous: TimeMemoryProfile | None,
    ) -> TimeMemoryProfile:
        current = now.astimezone(UTC)
        windows = {
            cast(WindowName, f"{days}d"): self._window(
                days=days, timezone_name=timezone_name, now=current, source=source
            )
            for days in self.config.window_days
        }
        places = self._common_places(source.events, now=current, timezone_name=timezone_name)
        patterns = self._stable_patterns(
            windows=windows,
            places=places,
            events=source.events,
            now=current,
            previous=previous,
        )
        summaries = [pattern.summary for pattern in patterns if pattern.status == "active"][:5]
        return TimeMemoryProfile(
            schema_version=self.config.schema_version,
            user_id=user_id,
            generated_at=current,
            data_until=current,
            timezone=timezone_name,
            common_places=places,
            behavior_windows=windows,
            stable_patterns=patterns,
            profile_summary=" ".join(summaries),
            version=(previous.version + 1 if previous else 1),
        )

    def _window(
        self,
        *,
        days: int,
        timezone_name: str,
        now: datetime,
        source: TimeMemorySourceData,
    ) -> BehaviorWindow:
        start_date, end_date, start = _window_bounds(now, timezone_name, days)
        events = [
            event
            for event in source.events
            if event.status != CalendarEventStatus.CANCELLED
            and event.end_at >= start
            and event.start_at <= now
        ]
        changes = [change for change in source.changes if start <= change.occurred_at <= now]
        tasks = [task for task in source.tasks if start <= task.created_at <= now]
        reminders = [
            reminder for reminder in source.reminders if start <= reminder.created_at <= now
        ]
        completed_tasks = [
            task
            for task in source.tasks
            if task.completed_at is not None and start <= task.completed_at <= now
        ]
        cancelled_tasks = [
            change
            for change in changes
            if change.entity_type == MemoryEntityType.TASK
            and change.operation == MemoryOperation.CANCELLED
        ]
        schedule = self._schedule_pattern(
            events=events,
            days=days,
            start=start,
            end=now,
            timezone_name=timezone_name,
        )
        planning = self._planning_pattern(
            events=events, changes=changes, timezone_name=timezone_name
        )
        change_pattern = self._change_pattern(changes, len(events))
        sample_minimum = {7: 3, 30: 8, 180: 20}[days]
        confidence = min(1.0, len(events) / sample_minimum) if sample_minimum else 0
        summaries = [
            item for item in (schedule.summary, planning.summary, change_pattern.summary) if item
        ]
        return BehaviorWindow(
            window=cast(WindowName, f"{days}d"),
            start_date=start_date,
            end_date=end_date,
            sample_days=days,
            event_count=len(events),
            task_count=len(tasks),
            reminder_count=len(reminders),
            completed_task_count=len(completed_tasks),
            cancelled_task_count=len(cancelled_tasks),
            source_distribution=dict(Counter(change.source for change in changes)),
            schedule_pattern=schedule,
            planning_pattern=planning,
            change_pattern=change_pattern,
            summary=" ".join(summaries),
            confidence=confidence,
        )

    def _schedule_pattern(
        self,
        *,
        events: list[CalendarEvent],
        days: int,
        start: datetime,
        end: datetime,
        timezone_name: str,
    ) -> SchedulePattern:
        daily, _, hours = _daily_union_minutes(
            events, start=start, end=end, timezone_name=timezone_name
        )
        all_dates = [
            start.astimezone(ZoneInfo(timezone_name)).date() + timedelta(days=i)
            for i in range(days)
        ]
        values = [daily.get(day, 0) / 60 for day in all_dates]
        busy = [value >= self.config.busy_day_hours for value in values]
        longest = current = 0
        for is_busy in busy:
            current = current + 1 if is_busy else 0
            longest = max(longest, current)
        weekday = [value for day, value in zip(all_dates, values, strict=True) if day.weekday() < 5]
        weekend = [
            value for day, value in zip(all_dates, values, strict=True) if day.weekday() >= 5
        ]
        total = sum(values)
        if len(events) < 3:
            balance = "insufficient_data"
            summary = "当前日程样本不足，暂时无法判断安排强度。"
        elif sum(busy) >= max(3, days // 2):
            balance = "overloaded"
            summary = "该时段日程安排较密集，可在规划时主动保留空闲时段。"
        elif total / days >= self.config.light_day_hours:
            balance = "slightly_busy"
            summary = "该时段有一定日程负荷，但仍存在可调整空间。"
        else:
            balance = "balanced"
            summary = "该时段日程占用相对均衡。"
        return SchedulePattern(
            total_scheduled_hours=round(total, 2),
            average_daily_scheduled_hours=round(total / days, 2),
            median_daily_scheduled_hours=round(median(values), 2),
            scheduled_day_count=sum(value > 0 for value in values),
            busy_day_count=sum(busy),
            light_day_count=sum(
                self.config.light_day_hours <= value < self.config.busy_day_hours
                for value in values
            ),
            rest_day_count=sum(value < self.config.rest_day_hours for value in values),
            consecutive_busy_days_max=longest,
            weekday_average_hours=round(sum(weekday) / len(weekday), 2) if weekday else 0,
            weekend_average_hours=round(sum(weekend) / len(weekend), 2) if weekend else 0,
            peak_time_ranges=[
                f"{hour:02d}:00-{(hour + 1) % 24:02d}:00" for hour, _ in hours.most_common(3)
            ],
            work_rest_balance=cast(AnyBalance, balance),
            summary=summary,
        )

    def _planning_pattern(
        self,
        *,
        events: list[CalendarEvent],
        changes: list[ScheduleChange],
        timezone_name: str,
    ) -> PlanningPattern:
        creations = [
            change
            for change in changes
            if change.entity_type == MemoryEntityType.EVENT
            and change.operation == MemoryOperation.CREATED
        ]
        sessions = _creation_sessions(creations, self.config.planning_session_gap_minutes)
        batch_sessions = []
        batch_event_ids: set[object] = set()
        for session in sessions:
            dates = {
                value.astimezone(ZoneInfo(timezone_name)).date()
                for value in (
                    _parse_datetime(change.new_snapshot.get("start_at")) for change in session
                )
                if value is not None
            }
            if len(session) >= self.config.batch_planning_minimum and len(dates) >= 2:
                batch_sessions.append(session)
                batch_event_ids.update(change.entity_id for change in session)
        ratio = len(batch_event_ids) / len(creations) if creations else 0
        lead_times = [
            (event.start_at - event.created_at).total_seconds() / 3600
            for event in events
            if event.start_at >= event.created_at
        ]
        creation_hours = Counter(
            change.occurred_at.astimezone(ZoneInfo(timezone_name)).hour for change in creations
        )
        if len(creations) < 3:
            style = "insufficient_data"
            summary = "当前新增日程样本不足，暂时无法判断规划方式。"
        elif ratio >= 0.6:
            style, summary = "batch", "你近期倾向于集中批量规划多个日期的日程。"
        elif ratio <= 0.25:
            style, summary = "incremental", "你近期更倾向于逐步添加日程。"
        else:
            style, summary = "mixed", "你近期同时采用批量规划和逐步添加。"
        return PlanningPattern(
            created_event_count=len(creations),
            creation_session_count=len(sessions),
            batch_creation_session_count=len(batch_sessions),
            batch_creation_ratio=ratio,
            incremental_creation_ratio=1 - ratio if creations else 0,
            average_lead_time_hours=round(sum(lead_times) / len(lead_times), 2)
            if lead_times
            else 0,
            median_lead_time_hours=round(median(lead_times), 2) if lead_times else 0,
            last_minute_creation_ratio=(
                sum(value < 24 for value in lead_times) / len(lead_times) if lead_times else 0
            ),
            long_horizon_creation_ratio=(
                sum(value >= 168 for value in lead_times) / len(lead_times) if lead_times else 0
            ),
            typical_creation_time_ranges=[
                f"{hour:02d}:00-{(hour + 1) % 24:02d}:00"
                for hour, _ in creation_hours.most_common(3)
            ],
            planning_style=cast(AnyPlanningStyle, style),
            summary=summary,
        )

    def _change_pattern(self, changes: list[ScheduleChange], event_count: int) -> ChangePattern:
        event_changes = [
            change for change in changes if change.entity_type == MemoryEntityType.EVENT
        ]
        updates = [
            change for change in event_changes if change.operation == MemoryOperation.UPDATED
        ]
        deltas: list[float] = []
        for change in updates:
            old = _parse_datetime(change.old_snapshot.get("start_at"))
            new = _parse_datetime(change.new_snapshot.get("start_at"))
            if old is not None and new is not None and old != new:
                deltas.append((new - old).total_seconds() / 3600)
        cancelled = sum(change.operation == MemoryOperation.CANCELLED for change in event_changes)
        completed = sum(change.operation == MemoryOperation.COMPLETED for change in event_changes)
        rescheduled = len(deltas)
        denominator = max(event_count + cancelled, 1)
        if len(event_changes) < 3:
            dominant = "insufficient_data"
        elif cancelled / denominator >= 0.3:
            dominant = "cancel"
        elif rescheduled / denominator >= 0.3:
            dominant = (
                "postpone"
                if sum(deltas) > 0
                else "advance"
                if sum(deltas) < 0
                else "frequent_adjustment"
            )
        else:
            dominant = "stable"
        summaries = {
            "insufficient_data": "当前变更样本不足，暂时无法判断调整习惯。",
            "cancel": "近期取消日程的比例较高。",
            "postpone": "近期日程调整主要表现为向后推迟。",
            "advance": "近期日程调整主要表现为提前。",
            "frequent_adjustment": "近期日程时间调整较频繁。",
            "stable": "近期日程时间整体较稳定。",
        }
        return ChangePattern(
            modified_event_count=len(updates),
            rescheduled_event_count=rescheduled,
            postponed_event_count=sum(value > 0 for value in deltas),
            advanced_event_count=sum(value < 0 for value in deltas),
            cancelled_event_count=cancelled,
            completed_event_count=completed,
            reschedule_ratio=rescheduled / denominator,
            postpone_ratio=sum(value > 0 for value in deltas) / max(rescheduled, 1),
            cancellation_ratio=cancelled / denominator,
            completion_ratio=completed / denominator if event_count or cancelled else None,
            average_reschedule_delta_hours=round(
                sum(abs(value) for value in deltas) / len(deltas), 2
            )
            if deltas
            else 0,
            dominant_change_behavior=cast(AnyChangeBehavior, dominant),
            summary=summaries[dominant],
        )

    def _common_places(
        self, events: tuple[CalendarEvent, ...], *, now: datetime, timezone_name: str
    ) -> list[CommonPlace]:
        grouped: dict[str, list[CalendarEvent]] = {}
        cutoff = now - timedelta(days=self.config.history_days)
        for event in events:
            normalized = " ".join(event.location.casefold().split())
            if (
                normalized
                and event.status != CalendarEventStatus.CANCELLED
                and event.end_at >= cutoff
            ):
                grouped.setdefault(normalized, []).append(event)
        candidates: list[CommonPlace] = []
        max_count = max((len(values) for values in grouped.values()), default=1)
        for normalized, values in grouped.items():
            last_seen = max(event.end_at for event in values)
            recent_count = sum(
                event.end_at >= now - timedelta(days=self.config.place_weak_after_days)
                for event in values
            )
            if len(values) < self.config.min_place_event_count:
                continue
            if recent_count <= 1:
                continue
            hours = sum((event.end_at - event.start_at).total_seconds() for event in values) / 3600
            recency = max(0.0, 1 - (now - last_seen).days / self.config.history_days)
            confidence = min(1.0, len(values) / 10)
            score = (
                0.4 * (len(values) / max_count)
                + 0.25 * min(1.0, hours / 40)
                + 0.2 * recency
                + 0.15 * confidence
            )
            weekdays = Counter(
                event.start_at.astimezone(ZoneInfo(timezone_name)).weekday() for event in values
            )
            hours_counter = Counter(
                event.start_at.astimezone(ZoneInfo(timezone_name)).hour for event in values
            )
            candidates.append(
                CommonPlace(
                    place_id=normalized.replace(" ", "_")[:80],
                    name=values[-1].location.strip(),
                    normalized_name=normalized,
                    event_count=len(values),
                    total_scheduled_hours=round(hours, 2),
                    typical_weekdays=[day for day, _ in weekdays.most_common(3)],
                    typical_time_ranges=[
                        f"{hour:02d}:00-{(hour + 1) % 24:02d}:00"
                        for hour, _ in hours_counter.most_common(3)
                    ],
                    first_seen_at=min(event.start_at for event in values),
                    last_seen_at=last_seen,
                    confidence=confidence,
                    score=min(1.0, score),
                )
            )
        return sorted(candidates, key=lambda item: (item.score, item.last_seen_at), reverse=True)[
            : self.config.common_place_limit
        ]

    def _stable_patterns(
        self,
        *,
        windows: dict[WindowName, BehaviorWindow],
        places: list[CommonPlace],
        events: tuple[CalendarEvent, ...],
        now: datetime,
        previous: TimeMemoryProfile | None,
    ) -> list[StablePattern]:
        month, long = windows["30d"], windows["180d"]
        candidates: dict[str, tuple[str, str, float]] = {}
        if (
            month.confidence >= self.config.stable_pattern_min_confidence
            and long.confidence >= self.config.stable_pattern_min_confidence
            and month.schedule_pattern.work_rest_balance == long.schedule_pattern.work_rest_balance
            and month.schedule_pattern.work_rest_balance not in {"insufficient_data"}
        ):
            candidates["schedule.work_rest"] = ("schedule", month.schedule_pattern.summary, 0.78)
        if (
            month.confidence >= self.config.stable_pattern_min_confidence
            and long.confidence >= self.config.stable_pattern_min_confidence
            and month.planning_pattern.planning_style == long.planning_pattern.planning_style
            and month.planning_pattern.planning_style not in {"insufficient_data"}
        ):
            candidates["planning.style"] = ("planning", month.planning_pattern.summary, 0.8)
        if (
            month.confidence >= self.config.stable_pattern_min_confidence
            and long.confidence >= self.config.stable_pattern_min_confidence
            and month.change_pattern.dominant_change_behavior
            == long.change_pattern.dominant_change_behavior
            and month.change_pattern.dominant_change_behavior not in {"insufficient_data"}
        ):
            candidates["change.behavior"] = ("change", month.change_pattern.summary, 0.75)
        recent_place_counts = Counter(
            " ".join(event.location.casefold().split())
            for event in events
            if event.status != CalendarEventStatus.CANCELLED
            and event.end_at >= now - timedelta(days=30)
            and event.location.strip()
        )
        if (
            places
            and recent_place_counts[places[0].normalized_name] >= self.config.min_place_event_count
            and places[0].confidence >= self.config.stable_pattern_min_confidence
        ):
            candidates["place.common"] = (
                "place",
                f"常用地点包括“{places[0].name}”。",
                max(0.7, places[0].confidence),
            )
        previous_by_id = (
            {pattern.pattern_id: pattern for pattern in previous.stable_patterns}
            if previous
            else {}
        )
        results: list[StablePattern] = []
        for pattern_id, (pattern_type, summary, confidence) in candidates.items():
            old = previous_by_id.get(pattern_id)
            results.append(
                StablePattern(
                    pattern_id=pattern_id,
                    pattern_type=cast(AnyPatternType, pattern_type),
                    summary=summary,
                    evidence_windows=["30d", "180d"],
                    confidence=confidence,
                    first_detected_at=old.first_detected_at if old else now,
                    last_confirmed_at=now,
                    status="active",
                    score=confidence,
                )
            )
        for pattern_id, old in previous_by_id.items():
            if pattern_id in candidates or old.status == "expired":
                continue
            effective_cycle = now - old.last_confirmed_at >= timedelta(days=7)
            unsupported = old.unsupported_rebuild_count + (1 if effective_cycle else 0)
            status = (
                "expired"
                if unsupported >= self.config.stable_pattern_expire_rebuilds
                or old.confidence < self.config.stable_pattern_min_confidence
                or long.confidence < self.config.stable_pattern_min_confidence
                else "weakening"
            )
            results.append(
                old.model_copy(update={"unsupported_rebuild_count": unsupported, "status": status})
            )
        return results


type AnyBalance = Literal["balanced", "slightly_busy", "overloaded", "insufficient_data"]
type AnyPlanningStyle = Literal["batch", "incremental", "mixed", "insufficient_data"]
type AnyChangeBehavior = Literal[
    "stable", "postpone", "advance", "cancel", "frequent_adjustment", "insufficient_data"
]
type AnyPatternType = Literal["schedule", "planning", "change", "place"]
