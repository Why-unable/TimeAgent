from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from langgraph.store.memory import InMemoryStore

from apps.preferences.services import UserPreferenceService
from apps.tasks.execution_services import RecordExecutionSignalCommand, TaskExecutionSignalService
from apps.tasks.models import TaskExecutionSignalType
from apps.tasks.services import CreateTaskCommand, TaskService
from apps.time_memory.benchmark import benchmark_duration_profile
from apps.time_memory.decision_profile import DecisionProfileService
from apps.time_memory.updater import TimeMemoryUpdater

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


def test_longitudinal_memory_calibration_changes_next_day_duration_decision() -> None:
    enabled_user = User.objects.create_user("longitudinal-memory-enabled")
    disabled_user = User.objects.create_user("longitudinal-memory-disabled")
    UserPreferenceService.update_for_user(
        enabled_user,
        {
            "timezone": "Asia/Shanghai",
            "time_memory_enabled": True,
            "time_memory_allow_generation": True,
            "time_memory_allow_context_injection": True,
        },
    )
    UserPreferenceService.update_for_user(
        disabled_user,
        {
            "timezone": "Asia/Shanghai",
            "time_memory_enabled": False,
            "time_memory_allow_generation": False,
            "time_memory_allow_context_injection": False,
        },
    )

    target_anchor = timezone.now() + timedelta(days=1)
    start = target_anchor - timedelta(days=7)
    stores = {enabled_user.pk: InMemoryStore(), disabled_user.pk: InMemoryStore()}
    targets = {}
    for user in (enabled_user, disabled_user):
        for index in range(5):
            task_start = start + timedelta(days=index)
            task = TaskService.create_task(
                CreateTaskCommand(
                    user=user,
                    title=f"Write report draft {index}",
                    project="writing",
                    estimated_minutes=60,
                )
            )
            TaskExecutionSignalService.record(
                RecordExecutionSignalCommand(
                    user=user,
                    task_id=task.pk,
                    signal_type=TaskExecutionSignalType.STARTED,
                    occurred_at=task_start,
                    idempotency_key=f"longitudinal-start-{user.pk}-{index}",
                )
            )
            TaskExecutionSignalService.record(
                RecordExecutionSignalCommand(
                    user=user,
                    task_id=task.pk,
                    signal_type=TaskExecutionSignalType.COMPLETED,
                    occurred_at=task_start + timedelta(minutes=90),
                    idempotency_key=f"longitudinal-complete-{user.pk}-{index}",
                )
            )
        targets[user.pk] = TaskService.create_task(
            CreateTaskCommand(
                user=user,
                title="Write report draft for next week",
                project="writing",
                estimated_minutes=60,
            )
        )

    rebuilt = TimeMemoryUpdater.rebuild(
        user=enabled_user,
        store=stores[enabled_user.pk],
        now=target_anchor,
    )
    assert rebuilt is not None
    assert rebuilt.behavior_windows["30d"].execution_calibration.sample_count == 5
    assert (
        TimeMemoryUpdater.rebuild(
            user=disabled_user,
            store=stores[disabled_user.pk],
            now=target_anchor,
        )
        is None
    )

    enabled = DecisionProfileService.recommend_duration(
        user=enabled_user,
        store=stores[enabled_user.pk],
        task_id=targets[enabled_user.pk].pk,
        now=target_anchor,
    )
    disabled = DecisionProfileService.recommend_duration(
        user=disabled_user,
        store=stores[disabled_user.pk],
        task_id=targets[disabled_user.pk].pk,
        now=target_anchor,
    )

    assert enabled.recommended_minutes == 90
    assert enabled.sample_count == 5
    assert disabled.recommended_minutes == 60
    assert disabled.source == "user_disabled"
    assert abs(enabled.recommended_minutes - 90) == 0
    assert abs(disabled.recommended_minutes - 90) == 30
