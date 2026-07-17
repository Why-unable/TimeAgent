from datetime import UTC, date, datetime, time, timedelta

from django.contrib.auth.models import User

from apps.events.models import CalendarEvent, CalendarEventStatus
from apps.planning.schemas import PlanningConstraints, TimeSlot
from apps.preferences.models import UserPreference
from apps.tasks.models import Task, TaskStatus
from common.time import get_timezone, resolve_local_datetime, to_utc

BusyInterval = tuple[datetime, datetime]


class PlanningService:
    @staticmethod
    def find_free_slots(
        *,
        user: User,
        range_start: datetime,
        range_end: datetime,
        duration_minutes: int,
        constraints: PlanningConstraints | None = None,
    ) -> list[TimeSlot]:
        PlanningService._ensure_persisted_user(user)
        range_start_utc = to_utc(range_start)
        range_end_utc = to_utc(range_end)
        if range_end_utc <= range_start_utc:
            raise ValueError("range_end must be later than range_start")
        if duration_minutes < 1 or duration_minutes > 1440:
            raise ValueError("duration_minutes must be between 1 and 1440")

        constraints = constraints or PlanningConstraints()
        constraints.validate()
        preference = UserPreference.objects.filter(user=user).first() or UserPreference(user=user)
        timezone_name = constraints.timezone or preference.timezone
        user_timezone = get_timezone(timezone_name)
        daily_start = constraints.daily_start or preference.workday_start
        daily_end = constraints.daily_end or preference.workday_end
        if daily_end <= daily_start:
            raise ValueError("daily_end must be later than daily_start")

        busy_intervals = PlanningService._load_busy_intervals(
            user=user,
            range_start=range_start_utc,
            range_end=range_end_utc,
            include_planned_tasks=constraints.include_planned_tasks,
        )
        duration = timedelta(minutes=duration_minutes)
        increment = timedelta(minutes=constraints.slot_increment_minutes)
        local_start_date = range_start_utc.astimezone(user_timezone).date()
        local_end_date = range_end_utc.astimezone(user_timezone).date()
        slots: list[TimeSlot] = []

        current_date = local_start_date
        while current_date <= local_end_date:
            if current_date.weekday() in constraints.allowed_weekdays:
                window_start, window_end = PlanningService._daily_window(
                    current_date=current_date,
                    daily_start=daily_start,
                    daily_end=daily_end,
                    timezone_name=timezone_name,
                    range_start=range_start_utc,
                    range_end=range_end_utc,
                )
                if window_start < window_end:
                    PlanningService._append_window_slots(
                        slots=slots,
                        window_start=window_start,
                        window_end=window_end,
                        busy_intervals=busy_intervals,
                        duration=duration,
                        increment=increment,
                        max_results=constraints.max_results,
                    )
                    if (
                        constraints.max_results is not None
                        and len(slots) >= constraints.max_results
                    ):
                        return slots
            current_date += timedelta(days=1)

        return slots

    @staticmethod
    def _load_busy_intervals(
        *,
        user: User,
        range_start: datetime,
        range_end: datetime,
        include_planned_tasks: bool,
    ) -> list[BusyInterval]:
        event_intervals = CalendarEvent.objects.filter(
            user=user,
            start_at__lt=range_end,
            end_at__gt=range_start,
        ).exclude(status=CalendarEventStatus.CANCELLED).values_list("start_at", "end_at")
        intervals = list(event_intervals)
        if include_planned_tasks:
            task_intervals = Task.objects.filter(
                user=user,
                status__in=(TaskStatus.PENDING, TaskStatus.IN_PROGRESS),
                planned_start_at__lt=range_end,
                planned_end_at__gt=range_start,
            ).values_list("planned_start_at", "planned_end_at")
            intervals.extend(
                (start_at, end_at)
                for start_at, end_at in task_intervals
                if start_at is not None and end_at is not None
            )
        return PlanningService._merge_intervals(intervals)

    @staticmethod
    def _merge_intervals(intervals: list[BusyInterval]) -> list[BusyInterval]:
        merged: list[BusyInterval] = []
        for start_at, end_at in sorted(intervals):
            if not merged or start_at > merged[-1][1]:
                merged.append((start_at, end_at))
                continue
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end_at))
        return merged

    @staticmethod
    def _daily_window(
        *,
        current_date: date,
        daily_start: time,
        daily_end: time,
        timezone_name: str,
        range_start: datetime,
        range_end: datetime,
    ) -> BusyInterval:
        local_start = datetime.combine(current_date, daily_start)
        local_end = datetime.combine(current_date, daily_end)
        window_start = resolve_local_datetime(local_start, timezone_name, fold=0)
        window_end = resolve_local_datetime(local_end, timezone_name, fold=1)
        return max(window_start, range_start), min(window_end, range_end)

    @staticmethod
    def _append_window_slots(
        *,
        slots: list[TimeSlot],
        window_start: datetime,
        window_end: datetime,
        busy_intervals: list[BusyInterval],
        duration: timedelta,
        increment: timedelta,
        max_results: int | None,
    ) -> None:
        cursor = window_start
        for busy_start, busy_end in busy_intervals:
            if busy_end <= cursor:
                continue
            if busy_start >= window_end:
                break
            PlanningService._append_gap_slots(
                slots=slots,
                gap_start=cursor,
                gap_end=min(busy_start, window_end),
                duration=duration,
                increment=increment,
                max_results=max_results,
            )
            if max_results is not None and len(slots) >= max_results:
                return
            cursor = max(cursor, busy_end)
            if cursor >= window_end:
                return
        PlanningService._append_gap_slots(
            slots=slots,
            gap_start=cursor,
            gap_end=window_end,
            duration=duration,
            increment=increment,
            max_results=max_results,
        )

    @staticmethod
    def _append_gap_slots(
        *,
        slots: list[TimeSlot],
        gap_start: datetime,
        gap_end: datetime,
        duration: timedelta,
        increment: timedelta,
        max_results: int | None,
    ) -> None:
        candidate_start = gap_start
        while candidate_start + duration <= gap_end:
            slots.append(
                TimeSlot(
                    start_at=candidate_start.astimezone(UTC),
                    end_at=(candidate_start + duration).astimezone(UTC),
                )
            )
            if max_results is not None and len(slots) >= max_results:
                return
            candidate_start += increment

    @staticmethod
    def _ensure_persisted_user(user: User) -> None:
        if user.pk is None:
            raise ValueError("Planning user must be persisted")
