from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import User
from django.test import Client
from langgraph.store.memory import InMemoryStore

from apps.preferences.services import UserPreferenceService
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


def test_plan_edit_apply_task_detail_and_today_keep_one_time_instant() -> None:
    user = User.objects.create_user("time-consistency-api")
    UserPreferenceService.update_for_user(
        user,
        {
            "timezone": "Asia/Shanghai",
            "workday_start": time(9),
            "workday_end": time(23, 30),
        },
    )
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Evening task", estimated_minutes=30)
    )
    client = Client()
    client.force_login(user)
    planned = client.post(
        "/api/v1/planning/plans/",
        data={
            "task_ids": [str(task.pk)],
            "range_start": "2026-10-05T12:00:00Z",
            "range_end": "2026-10-05T16:00:00Z",
            "strategy": "plan_tasks_only",
        },
        content_type="application/json",
    )
    assert planned.status_code == 201
    plan = planned.json()
    edited = client.post(
        f"/api/v1/planning/plans/{plan['id']}/edit/",
        data={
            "expected_version": plan["version"],
            "items": [
                {
                    "task_id": str(task.pk),
                    "start_at": "2026-10-05T22:30:00+08:00",
                    "end_at": "2026-10-05T23:00:00+08:00",
                }
            ],
        },
        content_type="application/json",
    )
    assert edited.status_code == 200
    edited_plan = edited.json()
    plan_item = next(item for item in edited_plan["items"] if item.get("task_id"))
    expected_utc = datetime(2026, 10, 5, 14, 30, tzinfo=UTC)
    assert datetime.fromisoformat(plan_item["start_at"]) == expected_utc
    assert (
        datetime.fromisoformat(plan_item["start_at"])
        .astimezone(ZoneInfo("Asia/Shanghai"))
        .isoformat()
        == "2026-10-05T22:30:00+08:00"
    )

    applied = client.post(
        f"/api/v1/planning/plans/{plan['id']}/apply/",
        data={"expected_version": edited_plan["version"]},
        content_type="application/json",
    )
    assert applied.status_code == 200
    task_detail = client.get(f"/api/v1/tasks/{task.pk}/")
    assert task_detail.status_code == 200
    raw_task_start = task_detail.json()["planned_start_at"]
    assert raw_task_start == "2026-10-05T14:30:00Z"
    assert datetime.fromisoformat(raw_task_start.replace("Z", "+00:00")) == expected_utc

    with patch(
        "apps.today.services.timezone.now",
        return_value=datetime(2026, 10, 5, 12, 30, tzinfo=UTC),
    ):
        today = client.get("/api/v1/today/")
    assert today.status_code == 200
    today_task = next(item for item in today.json()["planned_tasks"] if item["id"] == str(task.pk))
    assert today_task["planned_start_at"] == raw_task_start
