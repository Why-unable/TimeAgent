from datetime import UTC, datetime

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.tasks.models import (
    InvalidTaskTransitionError,
    Task,
    TaskPriority,
    TaskStatus,
)

pytestmark = pytest.mark.django_db

FIXED_NOW = datetime(2026, 7, 20, 1, 0, tzinfo=UTC)
PLANNED_END = datetime(2026, 7, 20, 2, 0, tzinfo=UTC)


def create_user(username: str = "task-user") -> User:
    return get_user_model().objects.create_user(username=username)


def build_task(user: User, **changes: object) -> Task:
    values: dict[str, object] = {
        "user": user,
        "title": "Prepare project report",
    }
    values.update(changes)
    return Task(**values)


def test_task_defaults_and_normalized_fields() -> None:
    task = build_task(
        create_user(),
        title="  Prepare project report  ",
        project="  Launch  ",
        tags=[" work ", "report"],
        due_at=PLANNED_END,
    )

    task.full_clean()
    task.save()
    task.refresh_from_db()

    assert task.title == "Prepare project report"
    assert task.project == "Launch"
    assert task.tags == ["work", "report"]
    assert task.due_at == PLANNED_END
    assert task.status == TaskStatus.PENDING
    assert task.priority == TaskPriority.MEDIUM
    assert task.source == "local"
    assert task.buffer_before_minutes == 0
    assert task.buffer_after_minutes == 0
    assert task.planning_locked is False


def test_task_requires_aware_datetimes() -> None:
    naive = datetime(2026, 7, 20, 9, 0)
    task = build_task(
        create_user(),
        due_at=naive,
        planned_start_at=naive,
        planned_end_at=datetime(2026, 7, 20, 10, 0),
    )

    with pytest.raises(ValidationError) as error:
        task.full_clean()

    assert "due_at" in error.value.message_dict
    assert "planned_start_at" in error.value.message_dict
    assert "planned_end_at" in error.value.message_dict


@pytest.mark.parametrize(
    ("planned_start_at", "planned_end_at"),
    [
        (FIXED_NOW, None),
        (None, PLANNED_END),
        (PLANNED_END, FIXED_NOW),
    ],
)
def test_planned_time_range_must_be_complete_and_ordered(
    planned_start_at: datetime | None,
    planned_end_at: datetime | None,
) -> None:
    task = build_task(
        create_user(),
        planned_start_at=planned_start_at,
        planned_end_at=planned_end_at,
    )

    with pytest.raises(ValidationError) as error:
        task.full_clean()

    assert "planned_end_at" in error.value.message_dict


def test_task_state_transition_sequence() -> None:
    task = build_task(create_user())

    task.transition_to(TaskStatus.IN_PROGRESS, occurred_at=FIXED_NOW)
    task.transition_to(
        TaskStatus.PENDING,
        occurred_at=datetime(2026, 7, 20, 1, 10, tzinfo=UTC),
    )
    task.transition_to(
        TaskStatus.IN_PROGRESS,
        occurred_at=datetime(2026, 7, 20, 1, 20, tzinfo=UTC),
    )
    task.transition_to(TaskStatus.COMPLETED, occurred_at=PLANNED_END)

    task.full_clean()
    assert task.status == TaskStatus.COMPLETED
    assert task.actual_started_at == FIXED_NOW
    assert task.completed_at == PLANNED_END
    assert not task.can_transition_to(TaskStatus.PENDING)


def test_pending_task_can_be_completed_directly() -> None:
    task = build_task(create_user())

    task.transition_to(TaskStatus.COMPLETED, occurred_at=FIXED_NOW)

    task.full_clean()
    assert task.status == TaskStatus.COMPLETED
    assert task.completed_at == FIXED_NOW


def test_invalid_and_terminal_transitions_are_rejected() -> None:
    task = build_task(create_user())
    task.transition_to(TaskStatus.CANCELLED, occurred_at=FIXED_NOW)

    with pytest.raises(InvalidTaskTransitionError, match="Cannot transition"):
        task.transition_to(TaskStatus.PENDING, occurred_at=PLANNED_END)
    with pytest.raises(InvalidTaskTransitionError, match="explicit timezone"):
        build_task(create_user("naive-transition-user")).transition_to(
            TaskStatus.IN_PROGRESS,
            occurred_at=datetime(2026, 7, 20, 9, 0),
        )


def test_parent_task_must_share_user_and_cannot_form_cycle() -> None:
    user = create_user()
    parent = build_task(user, title="Parent")
    parent.full_clean()
    parent.save()
    cross_user_child = build_task(
        create_user("other-task-user"),
        parent_task=parent,
    )
    self_parent = build_task(user, title="Self parent")
    self_parent.parent_task = self_parent

    with pytest.raises(ValidationError) as cross_user_error:
        cross_user_child.full_clean()
    with pytest.raises(ValidationError) as cycle_error:
        self_parent.full_clean()

    assert "parent_task" in cross_user_error.value.message_dict
    assert "parent_task" in cycle_error.value.message_dict


@pytest.mark.parametrize("tags", [["", "work"], ["work", "work"], ["work", 1]])
def test_tags_must_be_unique_non_empty_strings(tags: list[object]) -> None:
    task = build_task(create_user(), tags=tags)

    with pytest.raises(ValidationError) as error:
        task.full_clean()

    assert "tags" in error.value.message_dict


def test_database_rejects_inconsistent_completed_timestamp() -> None:
    task = build_task(
        create_user(),
        status=TaskStatus.COMPLETED,
        completed_at=None,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            task.save()


def test_deleting_parent_keeps_subtask_and_clears_parent_reference() -> None:
    user = create_user()
    parent = build_task(user, title="Parent")
    parent.full_clean()
    parent.save()
    child = build_task(user, title="Child", parent_task=parent)
    child.full_clean()
    child.save()

    parent.delete()

    child.refresh_from_db()
    assert child.parent_task is None
