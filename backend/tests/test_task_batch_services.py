from datetime import UTC, datetime

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.tasks.services import CreateTaskCommand, TaskQuery, TaskService

pytestmark = pytest.mark.django_db


def test_create_tasks_is_atomic_when_one_member_is_invalid() -> None:
    user = get_user_model().objects.create_user(username="task-batch-user")

    with pytest.raises(ValidationError):
        TaskService.create_tasks(
            commands=[
                CreateTaskCommand(user=user, title="Prepare agenda"),
                CreateTaskCommand(
                    user=user,
                    title="Invalid planning range",
                    planned_start_at=datetime(2026, 7, 25, 9, tzinfo=UTC),
                ),
            ]
        )

    assert TaskService.list_tasks(query=TaskQuery(user=user)) == []
