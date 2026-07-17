from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from apps.tasks.models import Task, TaskPriority, TaskStatus
from apps.tasks.services import (
    CreateTaskCommand,
    TaskQuery,
    TaskService,
    UpdateTaskCommand,
)

pytestmark = pytest.mark.django_db

FIXED_NOW = datetime(2026, 7, 20, 1, 0, tzinfo=UTC)
PLANNED_END = datetime(2026, 7, 20, 2, 0, tzinfo=UTC)


def create_user(username: str = "task-service-user") -> User:
    return get_user_model().objects.create_user(username=username)


def create_task(user: User, **changes: object) -> Task:
    values: dict[str, object] = {"user": user, "title": "Prepare report"}
    values.update(changes)
    return TaskService.create_task(CreateTaskCommand(**values))  # type: ignore[arg-type]


def test_create_and_update_task_apply_validation() -> None:
    user = create_user()
    task = create_task(user, title="  Prepare report  ", tags=[" work "])

    updated = TaskService.update_task(
        UpdateTaskCommand(
            user=user,
            task_id=task.id,
            changes={"priority": TaskPriority.HIGH, "tags": ["work", "report"]},
        )
    )

    assert updated.title == "Prepare report"
    assert updated.priority == TaskPriority.HIGH
    assert updated.tags == ["work", "report"]


def test_update_task_rejects_state_and_planning_fields() -> None:
    user = create_user()
    task = create_task(user)

    with pytest.raises(ValueError, match="Unsupported task fields"):
        TaskService.update_task(
            UpdateTaskCommand(
                user=user,
                task_id=task.id,
                changes={"status": TaskStatus.COMPLETED},
            )
        )
    with pytest.raises(ValueError, match="Unsupported task fields"):
        TaskService.update_task(
            UpdateTaskCommand(
                user=user,
                task_id=task.id,
                changes={"planned_start_at": FIXED_NOW},
            )
        )


def test_complete_task_records_time_and_is_idempotent() -> None:
    user = create_user()
    task = create_task(user)

    completed = TaskService.complete_task(
        task_id=task.id,
        user=user,
        occurred_at=FIXED_NOW,
    )
    repeated = TaskService.complete_task(
        task_id=task.id,
        user=user,
        occurred_at=PLANNED_END,
    )

    assert completed.status == TaskStatus.COMPLETED
    assert completed.completed_at == FIXED_NOW
    assert repeated.completed_at == FIXED_NOW


def test_reschedule_task_validates_and_normalizes_range() -> None:
    user = create_user()
    task = create_task(user)

    rescheduled = TaskService.reschedule_task(
        task_id=task.id,
        user=user,
        planned_start_at=FIXED_NOW,
        planned_end_at=PLANNED_END,
    )

    assert rescheduled.planned_start_at == FIXED_NOW
    assert rescheduled.planned_end_at == PLANNED_END
    with pytest.raises(ValidationError):
        TaskService.reschedule_task(
            task_id=task.id,
            user=user,
            planned_start_at=PLANNED_END,
            planned_end_at=FIXED_NOW,
        )


def test_task_service_enforces_user_scope() -> None:
    owner = create_user()
    other = create_user("other-task-service-user")
    task = create_task(owner)

    with pytest.raises(Task.DoesNotExist):
        TaskService.complete_task(task_id=task.id, user=other, occurred_at=FIXED_NOW)


def test_list_tasks_filters_by_status_due_plan_and_user() -> None:
    user = create_user()
    other = create_user("task-query-other")
    matching = create_task(
        user,
        due_at=PLANNED_END,
        planned_start_at=FIXED_NOW,
        planned_end_at=PLANNED_END,
    )
    create_task(user, title="Later", due_at=PLANNED_END + timedelta(days=2))
    completed = create_task(
        user,
        title="Completed",
        due_at=PLANNED_END,
        planned_start_at=FIXED_NOW,
        planned_end_at=PLANNED_END,
    )
    TaskService.complete_task(task_id=completed.id, user=user, occurred_at=FIXED_NOW)
    create_task(other, title="Other user's task", due_at=PLANNED_END)

    tasks = TaskService.list_tasks(
        TaskQuery(
            user=user,
            statuses=(TaskStatus.PENDING,),
            due_before=PLANNED_END,
            planned_starts_before=FIXED_NOW + timedelta(minutes=1),
            planned_ends_after=FIXED_NOW,
        )
    )

    assert tasks == [matching]
