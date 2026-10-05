from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.test import Client

from apps.interactions.models import InteractionArtifact, InteractionStatus
from apps.tasks.execution_services import (
    ExecutionSignalIdempotencyConflictError,
    RecordExecutionSignalCommand,
    TaskExecutionSignalService,
)
from apps.tasks.models import Task, TaskExecutionSignal, TaskExecutionSignalType, TaskStatus
from apps.tasks.services import CreateTaskCommand, TaskService
from apps.time_memory.models import ScheduleChange

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


def test_reopening_a_completed_task_is_audited_and_idempotent() -> None:
    user = create_user("execution-reopen")
    task = create_task(user)
    TaskService.complete_task(task_id=task.pk, user=user, occurred_at=NOW)
    interaction = InteractionArtifact.objects.get(task=task, status=InteractionStatus.PENDING)

    first = record(
        user, task, TaskExecutionSignalType.REOPENED, NOW + timedelta(minutes=1), "undo-1"
    )
    repeated = record(
        user, task, TaskExecutionSignalType.REOPENED, NOW + timedelta(minutes=1), "undo-1"
    )

    task.refresh_from_db()
    interaction.refresh_from_db()
    assert first.pk == repeated.pk
    assert first.signal_type == TaskExecutionSignalType.REOPENED
    assert task.status == TaskStatus.PENDING
    assert task.completed_at is None
    assert interaction.status == InteractionStatus.ABANDONED
    change = ScheduleChange.objects.filter(entity_id=task.pk).latest("created_at")
    assert change.operation == "updated"
    assert change.old_snapshot["status"] == TaskStatus.COMPLETED
    assert change.new_snapshot["status"] == TaskStatus.PENDING


def test_task_can_be_completed_again_after_reopen_with_a_new_signal() -> None:
    user = create_user("execution-recomplete")
    task = create_task(user)
    first = TaskExecutionSignalService.record_completion(user=user, task_id=task.pk, now=NOW)
    replay = TaskExecutionSignalService.record_completion(
        user=user, task_id=task.pk, now=NOW + timedelta(minutes=5)
    )
    record(user, task, TaskExecutionSignalType.REOPENED, NOW + timedelta(minutes=10), "undo-2")
    second = TaskExecutionSignalService.record_completion(
        user=user, task_id=task.pk, now=NOW + timedelta(minutes=20)
    )

    task.refresh_from_db()
    assert first.pk == replay.pk
    assert second.pk != first.pk
    assert task.status == TaskStatus.COMPLETED
    assert (
        TaskExecutionSignal.objects.filter(
            task=task, signal_type=TaskExecutionSignalType.COMPLETED
        ).count()
        == 2
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


def test_reopened_signal_closes_the_previous_active_execution_segment() -> None:
    user = create_user("execution-reopen-summary")
    task = create_task(user)
    record(user, task, TaskExecutionSignalType.STARTED, NOW, "reopen-summary-start")
    TaskExecutionSignalService.record_completion(
        user=user,
        task_id=task.pk,
        now=NOW + timedelta(minutes=20),
    )
    record(
        user,
        task,
        TaskExecutionSignalType.REOPENED,
        NOW + timedelta(minutes=25),
        "reopen-summary-undo",
    )

    summary = TaskExecutionSignalService.summary(
        user=user,
        task_id=task.pk,
        now=NOW + timedelta(hours=2),
    )

    assert summary.active_seconds == 20 * 60
    assert summary.open_started_at is None
    assert summary.last_signal_type == TaskExecutionSignalType.REOPENED


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


def test_execution_signal_api_can_restore_a_completed_task_idempotently() -> None:
    user = create_user("execution-api-reopen")
    client = Client()
    client.force_login(user)
    task = create_task(user)
    TaskService.complete_task(task_id=task.pk, user=user, occurred_at=NOW)
    url = SIGNALS_URL.format(task.pk)
    payload = {
        "signal_type": "reopened",
        "occurred_at": "2026-08-23T09:01:00+08:00",
        "idempotency_key": "api-reopen-1",
        "source": "web",
    }

    response = client.post(url, data=payload, content_type="application/json")
    repeated = client.post(url, data=payload, content_type="application/json")
    task.refresh_from_db()

    assert response.status_code == 200
    assert response.json()["signal_type"] == "reopened"
    assert repeated.json()["id"] == response.json()["id"]
    assert task.status == TaskStatus.PENDING
    assert task.completed_at is None
