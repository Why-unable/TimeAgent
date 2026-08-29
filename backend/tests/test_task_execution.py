from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.test import Client

from apps.tasks.execution_services import (
    ExecutionSignalIdempotencyConflictError,
    RecordExecutionSignalCommand,
    TaskExecutionSignalService,
)
from apps.tasks.models import Task, TaskExecutionSignalType, TaskStatus
from apps.tasks.services import CreateTaskCommand, TaskService

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 8, 23, 1, 0, tzinfo=UTC)
SIGNALS_URL = "/api/v1/tasks/{}/execution-signals/"


def create_user(username: str = "execution-user") -> User:
    return get_user_model().objects.create_user(username=username)


def create_task(user: User) -> Task:
    return TaskService.create_task(CreateTaskCommand(user=user, title="Prepare report"))


def record(
    user: User,
    task: Task,
    signal_type: TaskExecutionSignalType,
    occurred_at: datetime,
    key: str | None = None,
) -> Any:
    return TaskExecutionSignalService.record(
        RecordExecutionSignalCommand(
            user=user,
            task_id=task.pk,
            signal_type=signal_type,
            occurred_at=occurred_at,
            idempotency_key=key or str(uuid4()),
        )
    )


def test_execution_signal_state_changes_are_audited_and_idempotent() -> None:
    user = create_user()
    task = create_task(user)
    key = "mobile-start-1"

    started = record(user, task, TaskExecutionSignalType.STARTED, NOW, key)
    repeated = record(user, task, TaskExecutionSignalType.STARTED, NOW, key)
    paused = record(
        user,
        task,
        TaskExecutionSignalType.PAUSED,
        NOW + timedelta(minutes=25),
    )

    task.refresh_from_db()
    assert started.pk == repeated.pk
    assert task.status == TaskStatus.PENDING
    assert [started.signal_type, paused.signal_type] == ["started", "paused"]


def test_idempotency_key_cannot_change_signal_meaning() -> None:
    user = create_user()
    task = create_task(user)
    record(user, task, TaskExecutionSignalType.STARTED, NOW, "same-key")

    with pytest.raises(ExecutionSignalIdempotencyConflictError):
        record(
            user,
            task,
            TaskExecutionSignalType.SKIPPED,
            NOW,
            "same-key",
        )


def test_idempotency_key_cannot_change_source_or_metadata() -> None:
    user = create_user("execution-idempotency-details")
    task = create_task(user)
    record_command = RecordExecutionSignalCommand(
        user=user,
        task_id=task.pk,
        signal_type=TaskExecutionSignalType.STARTED,
        occurred_at=NOW,
        idempotency_key="same-details-key",
        source="web",
        metadata={"screen": "tasks"},
    )
    TaskExecutionSignalService.record(record_command)

    with pytest.raises(ExecutionSignalIdempotencyConflictError):
        TaskExecutionSignalService.record(
            RecordExecutionSignalCommand(
                user=user,
                task_id=task.pk,
                signal_type=TaskExecutionSignalType.STARTED,
                occurred_at=NOW,
                idempotency_key="same-details-key",
                source="android",
                metadata={"screen": "tasks"},
            )
        )

    with pytest.raises(ExecutionSignalIdempotencyConflictError):
        TaskExecutionSignalService.record(
            RecordExecutionSignalCommand(
                user=user,
                task_id=task.pk,
                signal_type=TaskExecutionSignalType.STARTED,
                occurred_at=NOW,
                idempotency_key="same-details-key",
                source="web",
                metadata={"screen": "today"},
            )
        )


def test_execution_summary_reconstructs_active_seconds() -> None:
    user = create_user()
    task = create_task(user)
    record(user, task, TaskExecutionSignalType.STARTED, NOW)
    record(
        user,
        task,
        TaskExecutionSignalType.PAUSED,
        NOW + timedelta(minutes=25),
    )
    record(
        user,
        task,
        TaskExecutionSignalType.RESUMED,
        NOW + timedelta(minutes=40),
    )

    summary = TaskExecutionSignalService.summary(
        user=user,
        task_id=task.pk,
        now=NOW + timedelta(minutes=55),
    )

    assert summary.signal_count == 3
    assert summary.active_seconds == 40 * 60
    assert summary.evidence_status == "recording"


def test_execution_summary_compares_planned_block_and_estimate() -> None:
    user = create_user("execution-comparison")
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Planned work",
            estimated_minutes=30,
            planned_start_at=NOW,
            planned_end_at=NOW + timedelta(minutes=45),
        )
    )
    record(user, task, TaskExecutionSignalType.STARTED, NOW)
    record(
        user,
        task,
        TaskExecutionSignalType.PAUSED,
        NOW + timedelta(minutes=35),
    )
    summary = TaskExecutionSignalService.summary(
        user=user, task_id=task.pk, now=NOW + timedelta(hours=1)
    )
    assert summary.planned_seconds == 45 * 60
    assert summary.estimated_seconds == 30 * 60
    assert summary.variance_vs_plan_seconds == -10 * 60
    assert summary.variance_vs_estimate_seconds == 5 * 60


def test_execution_signal_api_is_user_scoped_and_returns_summary() -> None:
    user = create_user("execution-api-user")
    other = create_user("execution-api-other")
    client = Client()
    client.force_login(user)
    other_client = Client()
    other_client.force_login(other)
    task = create_task(user)
    url = SIGNALS_URL.format(task.pk)

    response = client.post(
        url,
        data={
            "signal_type": "started",
            "occurred_at": "2026-08-23T09:00:00+08:00",
            "idempotency_key": "api-start-1",
        },
        content_type="application/json",
    )
    repeated = client.post(
        url,
        data={
            "signal_type": "started",
            "occurred_at": "2026-08-23T09:00:00+08:00",
            "idempotency_key": "api-start-1",
        },
        content_type="application/json",
    )
    summary = client.get(f"/api/v1/tasks/{task.pk}/execution-summary/")
    hidden = other_client.get(url)

    assert response.status_code == 200
    assert repeated.status_code == 200
    assert response.json()["id"] == repeated.json()["id"]
    assert summary.status_code == 200
    assert summary.json()["signal_count"] == 1
    assert hidden.status_code == 404
