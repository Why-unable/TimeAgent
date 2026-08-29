from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.events.services import CreateEventCommand, EventService
from apps.planning.recommendations import FreeTimeRecommendationService

pytestmark = pytest.mark.django_db


def test_free_time_recommendation_excludes_existing_event() -> None:
    user = get_user_model().objects.create_user(username="free-time-user")
    start = datetime(2026, 8, 24, 1, tzinfo=UTC)
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Fixed meeting",
            start_at=start,
            end_at=start + timedelta(hours=1),
            timezone="Asia/Shanghai",
        )
    )
    result = FreeTimeRecommendationService.recommend(
        user=user,
        range_start=start,
        range_end=start + timedelta(hours=3),
        duration_minutes=60,
    )
    assert result["slots"]
    assert all(slot["start_at"] >= start + timedelta(hours=1) for slot in result["slots"])
    assert result["slots"][0]["reason_codes"] == ["within_work_hours", "no_existing_overlap"]


def test_free_time_recommendation_api_validates_duration_and_authentication() -> None:
    user = get_user_model().objects.create_user(username="free-time-api")
    client = Client()
    client.force_login(user)
    response = client.get(
        "/api/v1/planning/free-time-recommendations/",
        {
            "range_start": "2026-08-24T09:00:00+08:00",
            "range_end": "2026-08-24T18:00:00+08:00",
            "duration_minutes": "30",
        },
    )
    invalid = client.get(
        "/api/v1/planning/free-time-recommendations/",
        {
            "range_start": "2026-08-24T09:00:00+08:00",
            "range_end": "2026-08-24T18:00:00+08:00",
            "duration_minutes": "0",
        },
    )
    assert response.status_code == 200
    assert response.json()["timezone"] == "Asia/Shanghai"
    assert invalid.status_code == 400
