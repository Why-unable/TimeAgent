from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.tasks.execution_services import RecordExecutionSignalCommand, TaskExecutionSignalService
from apps.tasks.models import TaskExecutionSignalType
from apps.tasks.services import CreateTaskCommand, TaskService
from apps.time_memory.analyzer import TimeMemoryAnalyzer
from apps.time_memory.settings import TimeMemorySettings
from apps.time_memory.source_repository import TimeMemorySourceRepository

pytestmark = pytest.mark.django_db


def test_time_memory_derives_estimate_calibration_from_execution_signals() -> None:
    user = get_user_model().objects.create_user(username="memory-execution-user")
    now = timezone.now()
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Calibrate report", estimated_minutes=30)
    )
    TaskExecutionSignalService.record(
        RecordExecutionSignalCommand(
            user=user,
            task_id=task.pk,
            signal_type=TaskExecutionSignalType.STARTED,
            occurred_at=now - timedelta(minutes=50),
            idempotency_key="memory-start",
        )
    )
    TaskExecutionSignalService.record(
        RecordExecutionSignalCommand(
            user=user,
            task_id=task.pk,
            signal_type=TaskExecutionSignalType.COMPLETED,
            occurred_at=now,
            idempotency_key="memory-complete",
        )
    )

    source = TimeMemorySourceRepository.load(
        user=user,
        since=now - timedelta(days=7),
        until=now + timedelta(seconds=1),
    )
    profile = TimeMemoryAnalyzer(TimeMemorySettings()).build_profile(
        user_id=str(user.pk),
        timezone_name="Asia/Shanghai",
        now=now,
        source=source,
        previous=None,
    )

    calibration = profile.behavior_windows["7d"].execution_calibration
    assert calibration.sample_count == 1
    assert calibration.average_estimated_minutes == 30
    assert calibration.average_actual_minutes == 50
    assert calibration.median_actual_to_estimated_ratio == pytest.approx(50 / 30, rel=1e-3)
