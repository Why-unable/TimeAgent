from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User

from apps.events.models import CalendarEventStatus
from apps.events.services import CreateEventCommand, EventService
from apps.planning.schemas import PlanningConstraints, TimeSlot
from apps.planning.services import PlanningService
from apps.preferences.services import UserPreferenceService
from apps.tasks.services import CreateTaskCommand, TaskService
from common.time import NaiveDateTimeError

pytestmark = pytest.mark.django_db

LOCAL_TIMEZONE = ZoneInfo("Asia/Shanghai")


def create_user(username: str = "planning-user") -> User:
    return get_user_model().objects.create_user(username=username)


def local_datetime(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, day, hour, minute, tzinfo=LOCAL_TIMEZONE)


def create_event(
    user: User,
    *,
    title: str,
    start_at: datetime,
    end_at: datetime,
    status: CalendarEventStatus | str = CalendarEventStatus.CONFIRMED,
) -> None:
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title=title,
            start_at=start_at,
            end_at=end_at,
            timezone="Asia/Shanghai",
            status=status,
        )
    )


def test_find_free_slots_uses_preferences_events_and_planned_tasks() -> None:
    user = create_user()
    UserPreferenceService.update_for_user(
        user,
        {"workday_start": time(9), "workday_end": time(18)},
    )
    create_event(
        user,
        title="Meeting",
        start_at=local_datetime(20, 10),
        end_at=local_datetime(20, 11),
    )
    TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Focused task",
            planned_start_at=local_datetime(20, 13),
            planned_end_at=local_datetime(20, 14),
        )
    )

    slots = PlanningService.find_free_slots(
        user=user,
        range_start=local_datetime(20, 0),
        range_end=local_datetime(21, 0),
        duration_minutes=60,
        constraints=PlanningConstraints(slot_increment_minutes=60),
    )

    assert [slot.start_at.astimezone(LOCAL_TIMEZONE).hour for slot in slots] == [
        9,
        11,
        12,
        14,
        15,
        16,
        17,
    ]
    assert all(slot.end_at - slot.start_at == timedelta(hours=1) for slot in slots)


def test_free_slot_search_merges_busy_intervals_and_ignores_cancelled_events() -> None:
    user = create_user()
    create_event(
        user,
        title="First overlap",
        start_at=local_datetime(20, 9, 30),
        end_at=local_datetime(20, 11),
    )
    create_event(
        user,
        title="Second overlap",
        start_at=local_datetime(20, 10, 30),
        end_at=local_datetime(20, 12),
    )
    create_event(
        user,
        title="Cancelled",
        start_at=local_datetime(20, 12),
        end_at=local_datetime(20, 13),
        status=CalendarEventStatus.CANCELLED,
    )

    slots = PlanningService.find_free_slots(
        user=user,
        range_start=local_datetime(20, 9),
        range_end=local_datetime(20, 14),
        duration_minutes=60,
        constraints=PlanningConstraints(
            daily_start=time(9),
            daily_end=time(14),
            slot_increment_minutes=60,
        ),
    )

    assert slots == [
        TimeSlot(
            start_at=local_datetime(20, 12).astimezone(UTC),
            end_at=local_datetime(20, 13).astimezone(UTC),
        ),
        TimeSlot(
            start_at=local_datetime(20, 13).astimezone(UTC),
            end_at=local_datetime(20, 14).astimezone(UTC),
        ),
    ]


def test_free_slot_constraints_limit_days_results_and_task_inclusion() -> None:
    user = create_user()
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Optional planned task",
            planned_start_at=local_datetime(20, 9),
            planned_end_at=local_datetime(20, 10),
        )
    )

    slots = PlanningService.find_free_slots(
        user=user,
        range_start=local_datetime(20, 0),
        range_end=local_datetime(22, 0),
        duration_minutes=30,
        constraints=PlanningConstraints(
            daily_start=time(9),
            daily_end=time(10),
            allowed_weekdays=(0,),
            slot_increment_minutes=30,
            max_results=1,
            include_planned_tasks=False,
        ),
    )

    assert task.planned_start_at is not None
    assert slots == [
        TimeSlot(
            start_at=local_datetime(20, 9).astimezone(UTC),
            end_at=local_datetime(20, 9, 30).astimezone(UTC),
        )
    ]


def test_free_slot_search_respects_dst_day_length() -> None:
    user = create_user()
    new_york = ZoneInfo("America/New_York")

    slots = PlanningService.find_free_slots(
        user=user,
        range_start=datetime(2026, 3, 8, 0, tzinfo=new_york),
        range_end=datetime(2026, 3, 9, 0, tzinfo=new_york),
        duration_minutes=60,
        constraints=PlanningConstraints(
            timezone="America/New_York",
            daily_start=time(1),
            daily_end=time(4),
            slot_increment_minutes=60,
        ),
    )

    assert len(slots) == 2
    local_slot_hours = [
        (
            slot.start_at.astimezone(new_york).hour,
            slot.end_at.astimezone(new_york).hour,
        )
        for slot in slots
    ]
    assert local_slot_hours == [
        (1, 3),
        (3, 4),
    ]


@pytest.mark.parametrize(
    "constraints",
    [
        PlanningConstraints(daily_start=time(9)),
        PlanningConstraints(allowed_weekdays=()),
        PlanningConstraints(slot_increment_minutes=0),
        PlanningConstraints(max_results=0),
    ],
)
def test_free_slot_search_rejects_invalid_constraints(
    constraints: PlanningConstraints,
) -> None:
    user = create_user()

    with pytest.raises(ValueError):
        PlanningService.find_free_slots(
            user=user,
            range_start=local_datetime(20, 0),
            range_end=local_datetime(21, 0),
            duration_minutes=60,
            constraints=constraints,
        )


def test_free_slot_search_rejects_naive_range() -> None:
    user = create_user()

    with pytest.raises(NaiveDateTimeError):
        PlanningService.find_free_slots(
            user=user,
            range_start=datetime(2026, 7, 20, 9),
            range_end=local_datetime(21, 0),
            duration_minutes=60,
        )
