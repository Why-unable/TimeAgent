from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
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


def test_schedule_plan_lifecycle_api_edits_validates_and_abandons() -> None:
    user = User.objects.create_user("plan-lifecycle-api")
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Lifecycle task", estimated_minutes=30)
    )
    client = Client()
    client.force_login(user)
    created = client.post(
        "/api/v1/planning/plans/",
        data={
            "task_ids": [str(task.pk)],
            "range_start": datetime(2026, 7, 27, 1, tzinfo=UTC).isoformat(),
            "range_end": datetime(2026, 7, 27, 4, tzinfo=UTC).isoformat(),
            "strategy": "plan_tasks_only",
        },
        content_type="application/json",
    )
    assert created.status_code == 201
    plan = created.json()
    assert plan["constraints_snapshot"]["snapshot_version"] == "planning-constraints-v1"
    assert plan["expires_at"]

    edited = client.post(
        f"/api/v1/planning/plans/{plan['id']}/edit/",
        data={
            "expected_version": plan["version"],
            "items": [{"task_id": str(task.pk), "locked": True}],
        },
        content_type="application/json",
    )
    assert edited.status_code == 200
    edited_plan = edited.json()
    task_item = next(item for item in edited_plan["items"] if item.get("task_id"))
    assert task_item["locked"] is True

    validated = client.post(
        f"/api/v1/planning/plans/{plan['id']}/validate/",
        data={"expected_version": edited_plan["version"]},
        content_type="application/json",
    )
    assert validated.status_code == 200
    assert validated.json()["valid"] is True

    abandoned = client.post(
        f"/api/v1/planning/plans/{plan['id']}/abandon/",
        data={"expected_version": edited_plan["version"]},
        content_type="application/json",
    )
    assert abandoned.status_code == 200
    assert abandoned.json()["status"] == "abandoned"
