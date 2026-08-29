from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import Client
from langgraph.store.memory import InMemoryStore

from apps.tasks.services import CreateTaskCommand, TaskService

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def fake_planning_store() -> Iterator[None]:
    @contextmanager
    def fake_store() -> Iterator[InMemoryStore]:
        yield InMemoryStore()

    with patch("apps.planning.views.open_postgres_store", fake_store):
        yield


def test_schedule_plan_api_supports_preview_and_versioned_apply() -> None:
    user = User.objects.create_user("plan-api")
    start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Plan me",
            due_at=start + timedelta(hours=4),
            estimated_minutes=30,
        )
    )
    client = Client()
    client.force_login(user)
    response = client.post(
        "/api/v1/planning/plans/",
        data={
            "task_ids": [str(task.pk)],
            "range_start": start.isoformat(),
            "range_end": (start + timedelta(hours=8)).isoformat(),
            "strategy": "plan_tasks_only",
        },
        content_type="application/json",
    )
    assert response.status_code == 201
    payload = response.json()
    applied = client.post(
        f"/api/v1/planning/plans/{payload['id']}/apply/",
        data={"expected_version": payload["version"]},
        content_type="application/json",
    )
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"


def test_schedule_plan_api_supports_comparison_and_local_regeneration() -> None:
    user = User.objects.create_user("plan-api-compare")
    start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    tasks = [
        TaskService.create_task(
            CreateTaskCommand(user=user, title=f"Compare {index}", estimated_minutes=30)
        )
        for index in range(2)
    ]
    client = Client()
    client.force_login(user)
    payload = {
        "task_ids": [str(task.pk) for task in tasks],
        "range_start": start.isoformat(),
        "range_end": (start + timedelta(hours=8)).isoformat(),
        "strategy": "plan_tasks_only",
    }
    comparison = client.post(
        "/api/v1/planning/plans/compare/", data=payload, content_type="application/json"
    )
    assert comparison.status_code == 201
    assert len(comparison.json()["alternatives"]) == 2
    plan = comparison.json()["alternatives"][0]
    regenerated = client.post(
        f"/api/v1/planning/plans/{plan['id']}/regenerate/",
        data={
            "expected_version": plan["version"],
            "task_ids": [str(tasks[1].pk)],
            "ordering": "longest_first",
        },
        content_type="application/json",
    )
    assert regenerated.status_code == 200
    assert regenerated.json()["version"] == 2
