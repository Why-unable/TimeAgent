from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.events.services import CreateEventCommand, EventService
from apps.planning.models import AutomationPolicy, ScheduleChangeBatchStatus
from apps.tasks.services import CreateTaskCommand, TaskService

pytestmark = pytest.mark.django_db


def test_disruption_detection_api_returns_impact_timeline_facts() -> None:
    user = User.objects.create_user("adaptive-detect-api")
    start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Focus",
            planned_start_at=start,
            planned_end_at=start + timedelta(hours=1),
        )
    )
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Meeting",
            start_at=start + timedelta(minutes=20),
            end_at=start + timedelta(minutes=50),
            timezone="UTC",
        )
    )
    client = Client()
    client.force_login(user)

    response = client.post(
        "/api/v1/planning/disruptions/detect/",
        data={
            "range_start": start.isoformat(),
            "range_end": (start + timedelta(hours=2)).isoformat(),
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()[0]["task_id"] == str(task.pk)
    assert response.json()[0]["overlap_minutes"] == 30


def test_local_replan_preview_api_is_read_only() -> None:
    user = User.objects.create_user("adaptive-api")
    start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Move me",
            estimated_minutes=30,
            planned_start_at=start,
            planned_end_at=start + timedelta(minutes=30),
        )
    )
    client = Client()
    client.force_login(user)
    response = client.post(
        "/api/v1/planning/plans/local-replan-preview/",
        data={
            "blocked_start": start.isoformat(),
            "blocked_end": (start + timedelta(minutes=30)).isoformat(),
            "movable_task_ids": [str(task.pk)],
            "horizon_end": (start + timedelta(hours=8)).isoformat(),
        },
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["moved_items"][0]["state"] == "moved"
    assert response.json()["stability_cost"]["moved_count"] == 1
    task.refresh_from_db()
    assert task.planned_start_at == start


def test_local_replan_apply_api_requires_policy_consent_and_is_idempotent() -> None:
    user = User.objects.create_user("adaptive-apply-api")
    start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Move once",
            estimated_minutes=30,
            planned_start_at=start,
            planned_end_at=start + timedelta(minutes=30),
        )
    )
    policy = AutomationPolicy.objects.create(
        user=user,
        name="Auto move flexible tasks",
        enabled=True,
        allow_task_reschedule=True,
        max_moves_per_run=1,
        requires_approval=False,
    )
    operation_id = uuid4()
    payload = {
        "blocked_start": start.isoformat(),
        "blocked_end": (start + timedelta(minutes=30)).isoformat(),
        "movable_task_ids": [str(task.pk)],
        "horizon_end": (start + timedelta(hours=8)).isoformat(),
        "policy_id": str(policy.pk),
        "operation_id": str(operation_id),
    }
    client = Client()
    client.force_login(user)

    created = client.post(
        "/api/v1/planning/plans/local-replan-apply/",
        data=payload,
        content_type="application/json",
    )
    replayed = client.post(
        "/api/v1/planning/plans/local-replan-apply/",
        data=payload,
        content_type="application/json",
    )

    assert created.status_code == 201
    assert replayed.status_code == 200
    assert replayed.json()["id"] == created.json()["id"]
    assert created.json()["status"] == ScheduleChangeBatchStatus.APPLIED
    task.refresh_from_db()
    assert task.planned_start_at != start


def test_local_replan_apply_api_rejects_policy_that_requires_hitl() -> None:
    user = User.objects.create_user("adaptive-hitl-api")
    start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Needs review",
            estimated_minutes=30,
            planned_start_at=start,
            planned_end_at=start + timedelta(minutes=30),
        )
    )
    policy = AutomationPolicy.objects.create(
        user=user,
        name="Review every move",
        enabled=True,
        allow_task_reschedule=True,
        max_moves_per_run=1,
        requires_approval=True,
    )
    client = Client()
    client.force_login(user)
    response = client.post(
        "/api/v1/planning/plans/local-replan-apply/",
        data={
            "blocked_start": start.isoformat(),
            "blocked_end": (start + timedelta(minutes=30)).isoformat(),
            "movable_task_ids": [str(task.pk)],
            "horizon_end": (start + timedelta(hours=8)).isoformat(),
            "policy_id": str(policy.pk),
            "operation_id": str(uuid4()),
        },
        content_type="application/json",
    )

    assert response.status_code == 409
    task.refresh_from_db()
    assert task.planned_start_at == start
