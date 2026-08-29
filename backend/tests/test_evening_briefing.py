from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.briefings.evening import EveningBriefingService
from apps.insights.services import TemporalInsightService
from apps.tasks.services import CreateTaskCommand, TaskService

pytestmark = pytest.mark.django_db


def test_evening_preview_reuses_deterministic_insights_and_tasks() -> None:
    user = get_user_model().objects.create_user(username="evening-preview")
    now = datetime(2026, 8, 24, 10, tzinfo=UTC)
    TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Finish evening report",
            due_at=now + timedelta(hours=2),
            estimated_minutes=30,
        )
    )
    TemporalInsightService.scan(user=user, now=now)
    result = EveningBriefingService.build(user=user, now=now)
    assert result["target_date"].isoformat() == "2026-08-24"
    assert result["tasks"][0]["title"] == "Finish evening report"
    assert result["insights"][0]["kind"] == "deadline_risk"


def test_evening_preview_api_is_authenticated() -> None:
    client = Client()
    response = client.get("/api/v1/briefings/evening-preview/")
    assert response.status_code in {302, 401}
