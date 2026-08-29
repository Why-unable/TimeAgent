from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth.models import User

from apps.tasks.execution_services import RecordExecutionSignalCommand, TaskExecutionSignalService
from apps.tasks.models import TaskExecutionSignalType
from apps.tasks.services import CreateTaskCommand, TaskService
from apps.time_memory.benchmark import benchmark_duration_profile

pytestmark = pytest.mark.django_db


def test_duration_benchmark_reports_insufficient_data_without_inventing_metrics() -> None:
    user = User.objects.create_user("benchmark-small")
    result = benchmark_duration_profile(user=user)
    assert result.status == "insufficient_data"
    assert result.calibrated_mae is None


def test_duration_benchmark_uses_temporal_holdout() -> None:
    user = User.objects.create_user("benchmark-holdout")
    start = datetime(2026, 1, 1, 9, tzinfo=UTC)
    for index in range(10):
        task_start = start + timedelta(days=index)
        task = TaskService.create_task(
            CreateTaskCommand(
                user=user,
                title=f"Task {index}",
                estimated_minutes=30,
                due_at=task_start + timedelta(hours=2),
            )
        )
        TaskExecutionSignalService.record(
            RecordExecutionSignalCommand(
                user=user,
                task_id=task.pk,
                signal_type=TaskExecutionSignalType.STARTED,
                occurred_at=task_start,
                idempotency_key=f"start-{index}",
            )
        )
        TaskExecutionSignalService.record(
            RecordExecutionSignalCommand(
                user=user,
                task_id=task.pk,
                signal_type=TaskExecutionSignalType.COMPLETED,
                occurred_at=task_start + timedelta(minutes=45),
                idempotency_key=f"complete-{index}",
            )
        )
    result = benchmark_duration_profile(user=user)
    assert result.status == "ok"
    assert result.train_count == 7
    assert result.test_count == 3
    assert result.calibrated_mae is not None
    assert result.stratified_mae is not None
    assert result.confidence_calibration_error is not None
    assert result.calibration_bins


def test_duration_benchmark_uses_explicit_project_segments_with_fallback() -> None:
    user = User.objects.create_user("benchmark-segments")
    start = datetime(2026, 1, 1, 9, tzinfo=UTC)
    for index in range(12):
        task_start = start + timedelta(days=index)
        task = TaskService.create_task(
            CreateTaskCommand(
                user=user,
                title=f"Segmented {index}",
                project="writing" if index < 8 else "admin",
                estimated_minutes=30,
            )
        )
        TaskExecutionSignalService.record(
            RecordExecutionSignalCommand(
                user=user,
                task_id=task.pk,
                signal_type=TaskExecutionSignalType.STARTED,
                occurred_at=task_start,
                idempotency_key=f"seg-start-{index}",
            )
        )
        TaskExecutionSignalService.record(
            RecordExecutionSignalCommand(
                user=user,
                task_id=task.pk,
                signal_type=TaskExecutionSignalType.COMPLETED,
                occurred_at=task_start + timedelta(minutes=60 if index < 8 else 30),
                idempotency_key=f"seg-done-{index}",
            )
        )
    result = benchmark_duration_profile(user=user)
    assert result.segment_count == 1
    assert result.stratified_fallback_count == 4


def test_duration_benchmark_evaluates_semantic_fallback_separately() -> None:
    user = User.objects.create_user("benchmark-semantic-segments")
    start = datetime(2026, 1, 1, 9, tzinfo=UTC)
    for index in range(12):
        task_start = start + timedelta(days=index)
        task = TaskService.create_task(
            CreateTaskCommand(
                user=user,
                title=f"Draft report section {index}",
                project=f"one-off-project-{index}",
                estimated_minutes=30,
            )
        )
        TaskExecutionSignalService.record(
            RecordExecutionSignalCommand(
                user=user,
                task_id=task.pk,
                signal_type=TaskExecutionSignalType.STARTED,
                occurred_at=task_start,
                idempotency_key=f"semantic-start-{index}",
            )
        )
        TaskExecutionSignalService.record(
            RecordExecutionSignalCommand(
                user=user,
                task_id=task.pk,
                signal_type=TaskExecutionSignalType.COMPLETED,
                occurred_at=task_start + timedelta(minutes=60),
                idempotency_key=f"semantic-done-{index}",
            )
        )

    result = benchmark_duration_profile(user=user)

    assert result.segment_count == 0
    assert result.semantic_segment_count == 1
    assert result.stratified_fallback_count == 0
