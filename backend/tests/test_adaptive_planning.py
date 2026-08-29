from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth.models import User

from apps.events.services import CreateEventCommand, EventService
from apps.planning.adaptive import AdaptivePlanningService
from apps.planning.models import AutomationPolicy, ScheduleChangeBatchStatus
from apps.tasks.models import Task
from apps.tasks.services import CreateTaskCommand, TaskService

pytestmark = pytest.mark.django_db


def test_disruption_detection_reports_event_task_overlap_without_mutation() -> None:
    user = User.objects.create_user("adaptive-detect")
    start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Protected focus block",
            estimated_minutes=60,
            planned_start_at=start,
            planned_end_at=start + timedelta(hours=1),
        )
    )
    event = EventService.create_event(
        CreateEventCommand(
            user=user,
            title="New meeting",
            start_at=start + timedelta(minutes=15),
            end_at=start + timedelta(minutes=45),
            timezone="UTC",
        )
    )

    disruptions = AdaptivePlanningService.detect_disruptions(
        user=user,
        range_start=start,
        range_end=start + timedelta(hours=2),
    )

    assert len(disruptions) == 1
    assert disruptions[0].task_id == task.pk
    assert disruptions[0].event_id == event.pk
    assert disruptions[0].overlap_minutes == 30
    assert disruptions[0].reason_codes == ("calendar_event_overlaps_planned_task",)
    task.refresh_from_db()
    assert task.planned_start_at == start


def test_local_replan_is_preview_only_and_moves_only_explicit_task() -> None:
    user = User.objects.create_user("adaptive")
    start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Move me",
            estimated_minutes=60,
            planned_start_at=start,
            planned_end_at=start + timedelta(hours=1),
        )
    )
    preview = AdaptivePlanningService.preview_local_replan(
        user=user,
        blocked_start=start,
        blocked_end=start + timedelta(hours=1),
        movable_task_ids=[task.pk],
        horizon_end=start + timedelta(days=1),
    )
    assert preview.moved_items[0]["state"] == "moved"
    assert preview.stability_cost["moved_count"] == 1
    assert preview.stability_cost["total_move_minutes"] > 0
    task.refresh_from_db()
    assert task.planned_start_at == start


def test_local_replan_rolls_back_every_write_when_one_task_update_fails() -> None:
    user = User.objects.create_user("adaptive-rollback")
    start = datetime(2026, 8, 24, 1, tzinfo=UTC)
    tasks = [
        TaskService.create_task(
            CreateTaskCommand(
                user=user,
                title=f"Rollback {index}",
                estimated_minutes=30,
                planned_start_at=start,
                planned_end_at=start + timedelta(minutes=30),
            )
        )
        for index in range(2)
    ]
    preview = AdaptivePlanningService.preview_local_replan(
        user=user,
        blocked_start=start,
        blocked_end=start + timedelta(minutes=30),
        movable_task_ids=[task.pk for task in tasks],
        horizon_end=start + timedelta(hours=8),
    )
    policy = AutomationPolicy.objects.create(
        user=user,
        name="Rollback policy",
        enabled=True,
        allow_task_reschedule=True,
        max_moves_per_run=2,
        requires_approval=False,
    )
    original_reschedule = TaskService.reschedule_task
    calls = 0

    def fail_second(**kwargs: Any) -> Task:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated database write failure")
        return original_reschedule(**kwargs)

    with patch("apps.planning.adaptive.TaskService.reschedule_task", side_effect=fail_second):
        with pytest.raises(RuntimeError, match="simulated database write failure"):
            AdaptivePlanningService.apply_local_replan(
                user=user, policy=policy, preview=preview, operation_id=uuid4()
            )
    for task in tasks:
        task.refresh_from_db()
        assert task.planned_start_at == start
    assert policy.schedulechangebatch_set.count() == 0


def test_local_replan_apply_requires_policy_and_records_change_batch() -> None:
    user = User.objects.create_user("adaptive-apply")
    start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Move me",
            estimated_minutes=60,
            planned_start_at=start,
            planned_end_at=start + timedelta(hours=1),
        )
    )
    preview = AdaptivePlanningService.preview_local_replan(
        user=user,
        blocked_start=start,
        blocked_end=start + timedelta(hours=1),
        movable_task_ids=[task.pk],
        horizon_end=start + timedelta(days=1),
    )
    policy = AutomationPolicy.objects.create(
        user=user,
        name="Flexible tasks",
        enabled=True,
        allow_task_reschedule=True,
        max_moves_per_run=1,
        requires_approval=False,
    )
    batch = AdaptivePlanningService.apply_local_replan(
        user=user, policy=policy, preview=preview, operation_id=uuid4()
    )
    assert batch.status == ScheduleChangeBatchStatus.APPLIED
    task.refresh_from_db()
    assert task.planned_start_at != start
    reverted = AdaptivePlanningService.revert_batch(user=user, batch_id=batch.pk)
    assert reverted.status == ScheduleChangeBatchStatus.REVERTED
    task.refresh_from_db()
    assert task.planned_start_at == start


def test_local_replan_preview_keeps_multiple_moves_disjoint() -> None:
    user = User.objects.create_user("adaptive-disjoint")
    start = datetime(2026, 8, 24, 1, tzinfo=UTC)
    tasks = [
        TaskService.create_task(
            CreateTaskCommand(
                user=user,
                title=f"Move {index}",
                estimated_minutes=30,
                planned_start_at=start,
                planned_end_at=start + timedelta(minutes=30),
            )
        )
        for index in range(2)
    ]
    preview = AdaptivePlanningService.preview_local_replan(
        user=user,
        blocked_start=start,
        blocked_end=start + timedelta(minutes=30),
        movable_task_ids=[task.pk for task in tasks],
        horizon_end=start + timedelta(hours=8),
    )

    first, second = preview.moved_items
    assert first["state"] == second["state"] == "moved"
    assert str(first["to_end_at"]) <= str(second["to_start_at"])


def test_local_replan_apply_revalidates_schedule_after_preview() -> None:
    user = User.objects.create_user("adaptive-revalidate")
    start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Move around conflict",
            estimated_minutes=30,
            planned_start_at=start,
            planned_end_at=start + timedelta(minutes=30),
        )
    )
    preview = AdaptivePlanningService.preview_local_replan(
        user=user,
        blocked_start=start,
        blocked_end=start + timedelta(minutes=30),
        movable_task_ids=[task.pk],
        horizon_end=start + timedelta(hours=8),
    )
    target_start = datetime.fromisoformat(str(preview.moved_items[0]["to_start_at"]))
    target_end = datetime.fromisoformat(str(preview.moved_items[0]["to_end_at"]))
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title="New conflict",
            start_at=target_start,
            end_at=target_end,
            timezone="UTC",
        )
    )
    policy = AutomationPolicy.objects.create(
        user=user,
        name="Flexible but safe",
        enabled=True,
        allow_task_reschedule=True,
        max_moves_per_run=1,
        requires_approval=False,
    )

    with pytest.raises(ValueError, match="conflicts with current schedule"):
        AdaptivePlanningService.apply_local_replan(
            user=user,
            policy=policy,
            preview=preview,
            operation_id=uuid4(),
        )
    task.refresh_from_db()
    assert task.planned_start_at == start
