from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.interactions.models import InteractionStatus
from apps.planning.services import PlanningService
from apps.preferences.services import UserPreferenceService
from apps.tasks.models import TaskStatus
from apps.tasks.services import CreateTaskCommand, TaskService

pytestmark = pytest.mark.django_db


def test_plan_interaction_api_restores_timeline_artifact() -> None:
    user = get_user_model().objects.create_user(username="interaction-api-plan")
    UserPreferenceService.update_for_user(user, {"timezone": "UTC"})
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="API interaction plan", estimated_minutes=30)
    )
    now = datetime.now(UTC)
    plan = PlanningService.propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=now,
        range_end=now + timedelta(days=3),
        strategy="plan_tasks_only",
        now=now,
    )
    client = APIClient()
    client.force_authenticate(user=user)

    created = client.post(
        "/api/v1/interactions/",
        {"type": "plan_timeline_edit", "plan_id": str(plan.pk)},
        format="json",
    )
    restored = client.get(
        "/api/v1/interactions/",
        {"type": "plan_timeline_edit", "plan_id": str(plan.pk)},
    )

    assert created.status_code == 200, created.data
    assert created.data["type"] == "plan_timeline_edit"
    assert restored.status_code == 200, restored.data
    assert len(restored.data) == 1
    assert restored.data[0]["id"] == created.data["id"]


def test_priority_ranking_submission_updates_only_the_plan_order() -> None:
    user = get_user_model().objects.create_user(username="interaction-api-ranking")
    UserPreferenceService.update_for_user(user, {"timezone": "UTC"})
    tasks = [
        TaskService.create_task(
            CreateTaskCommand(user=user, title=f"Ranking task {index}", estimated_minutes=30)
        )
        for index in range(2)
    ]
    now = datetime.now(UTC)
    plan = PlanningService.propose_schedule_plan(
        user=user,
        task_ids=[task.pk for task in tasks],
        range_start=now + timedelta(days=1),
        range_end=now + timedelta(days=3),
        strategy="plan_tasks_only",
        now=now,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    created = client.post(
        "/api/v1/interactions/",
        {"type": "priority_ranking", "plan_id": str(plan.pk)},
        format="json",
    )
    assert created.status_code == 200, created.data

    submitted = client.post(
        f"/api/v1/interactions/{created.data['id']}/submit/",
        {
            "expected_version": created.data["version"],
            "action": "reorder",
            "values": {"ordered_task_ids": [str(task.pk) for task in reversed(tasks)]},
            "idempotency_key": str(uuid4()),
        },
        format="json",
    )

    assert submitted.status_code == 200, submitted.data
    assert submitted.data["accepted"] is True
    assert submitted.data["plan"]["version"] == plan.version + 1
    ranked = sorted(
        (
            item["task_id"],
            item["planning_order"],
        )
        for item in submitted.data["plan"]["items"]
        if item.get("kind") != "plan_evidence"
    )
    assert ranked == sorted(
        (
            str(task.pk),
            index,
        )
        for index, task in enumerate(reversed(tasks))
    )
    for task in tasks:
        task.refresh_from_db()
        assert task.priority == "medium"
        assert task.planned_start_at is None
        assert task.planned_end_at is None


def test_completion_api_creates_recoverable_feedback_artifact() -> None:
    user = get_user_model().objects.create_user(username="interaction-api-completion")
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="API interaction completion", estimated_minutes=30)
    )
    client = APIClient()
    client.force_authenticate(user=user)

    completed = client.post(f"/api/v1/tasks/{task.pk}/complete/")
    pending = client.get(
        "/api/v1/interactions/",
        {"type": "task_completion", "task_id": str(task.pk)},
    )

    assert completed.status_code == 200, completed.data
    assert completed.data["status"] == TaskStatus.COMPLETED
    assert pending.status_code == 200, pending.data
    assert len(pending.data) == 1
    assert pending.data[0]["task_id"] == str(task.pk)
    assert pending.data[0]["status"] == InteractionStatus.PENDING
