from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.tasks.services import CreateTaskCommand, TaskService
from apps.time_memory.capacity import CapacityForecastService

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
