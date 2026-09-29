from datetime import UTC, datetime, time, timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.events.services import CreateEventCommand, EventService
from apps.preferences.services import UserPreferenceService
from apps.tasks.services import CreateTaskCommand, TaskService
from apps.time_memory.capacity import CapacityForecast, CapacityForecastService

pytestmark = pytest.mark.django_db


def test_capacity_forecast_reports_unplanned_due_work_and_api_shape() -> None:
    user = User.objects.create_user("capacity")
    start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Unplanned work",
            due_at=start + timedelta(hours=2),
            estimated_minutes=600,
        )
    )
    forecast = CapacityForecastService.forecast(
        user=user, range_start=start, range_end=start + timedelta(hours=8)
    )
    assert forecast.risk == "over_capacity"
    client = Client()
    client.force_login(user)
    response = client.get("/api/v1/time-memory/me/capacity-forecast/")
    assert response.status_code == 200
    assert "reason_codes" in response.json()


def test_capacity_forecast_uses_remaining_capacity_without_double_counting_commitments() -> None:
    start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    end = start + timedelta(hours=8)

    def forecast_case(
        name: str,
        *,
        planned_minutes: int = 0,
        unplanned_minutes: int = 0,
        event_minutes: int = 0,
        planned_offset: timedelta = timedelta(hours=1),
        allowed_weekdays: tuple[int, ...] | None = None,
        weekend: bool = False,
    ) -> CapacityForecast:
        user = User.objects.create_user(name)
        UserPreferenceService.update_for_user(
            user,
            {"timezone": "UTC", "workday_start": time(9), "workday_end": time(17)},
        )
        if planned_minutes:
            TaskService.create_task(
                CreateTaskCommand(
                    user=user,
                    title="Committed task",
                    due_at=end,
                    estimated_minutes=planned_minutes,
                    planned_start_at=start + planned_offset,
                    planned_end_at=start + planned_offset + timedelta(minutes=planned_minutes),
                )
            )
        if unplanned_minutes:
            TaskService.create_task(
                CreateTaskCommand(
                    user=user,
                    title="Unplanned task",
                    due_at=end,
                    estimated_minutes=unplanned_minutes,
                )
            )
        if event_minutes:
            EventService.create_event(
                CreateEventCommand(
                    user=user,
                    title="Busy event",
                    start_at=start + timedelta(hours=1),
                    end_at=start + timedelta(hours=1, minutes=event_minutes),
                    timezone="UTC",
                )
            )
        forecast_start = start
        forecast_end = end
        if weekend:
            forecast_start = datetime(2026, 8, 29, 9, tzinfo=UTC)
            forecast_end = datetime(2026, 8, 29, 17, tzinfo=UTC)
        return CapacityForecastService.forecast(
            user=user,
            range_start=forecast_start,
            range_end=forecast_end,
            allowed_weekdays=allowed_weekdays,
        )

    empty = forecast_case("capacity-empty")
    only_committed = forecast_case("capacity-committed", planned_minutes=60)
    only_unplanned = forecast_case("capacity-unplanned", unplanned_minutes=60)
    committed_and_unplanned = forecast_case(
        "capacity-combined", planned_minutes=360, unplanned_minutes=60
    )
    exact_fill = forecast_case("capacity-exact", planned_minutes=420, unplanned_minutes=60)
    overloaded = forecast_case("capacity-over", planned_minutes=420, unplanned_minutes=90)
    due_in_range_plan_outside = forecast_case(
        "capacity-outside-plan",
        planned_minutes=60,
        planned_offset=-timedelta(hours=2),
    )
    event_blocked = forecast_case("capacity-event", event_minutes=60)
    weekend_closed = forecast_case("capacity-weekend-closed", weekend=True)
    weekend_open = forecast_case("capacity-weekend-open", allowed_weekdays=(5,), weekend=True)

    assert empty.total_schedulable_capacity_minutes == 480
    assert empty.remaining_free_minutes == empty.available_minutes == 480
    assert empty.committed_minutes == empty.unplanned_minutes == 0
    assert only_committed.total_schedulable_capacity_minutes == 480
    assert only_committed.committed_minutes == 60
    assert only_committed.remaining_free_minutes == 420
    assert only_unplanned.unplanned_minutes == 60
    assert only_unplanned.risk == "within_capacity"
    assert committed_and_unplanned.remaining_free_minutes == 120
    assert committed_and_unplanned.committed_minutes == 360
    assert committed_and_unplanned.unplanned_minutes == 60
    assert committed_and_unplanned.risk == "within_capacity"
    assert exact_fill.remaining_free_minutes == exact_fill.unplanned_minutes == 60
    assert exact_fill.risk == "tight"
    assert overloaded.risk == "over_capacity"
    assert due_in_range_plan_outside.committed_minutes == 0
    assert due_in_range_plan_outside.unplanned_minutes == 60
    assert event_blocked.total_schedulable_capacity_minutes == 420
    assert weekend_closed.total_schedulable_capacity_minutes == 0
    assert weekend_open.total_schedulable_capacity_minutes == 480
