from datetime import UTC, datetime

import pytest
from django.contrib.auth import get_user_model

from apps.planning.models import SchedulePlanStatus
from apps.planning.services import PlanningService
from apps.tasks.services import CreateTaskCommand, TaskService

pytestmark = pytest.mark.django_db


def test_propose_then_apply_task_schedule_plan() -> None:
    user = get_user_model().objects.create_user(username="plan-user")
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Write outline", estimated_minutes=30)
    )
    plan = PlanningService.propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=datetime(2026, 7, 27, 1, tzinfo=UTC),
        range_end=datetime(2026, 7, 28, 1, tzinfo=UTC),
        strategy="plan_tasks_only",
    )

    assert plan.status == SchedulePlanStatus.DRAFT
    applied = PlanningService.apply_schedule_plan(
        user=user,
        plan_id=plan.pk,
        expected_version=plan.version,
    )
    task.refresh_from_db()
    assert applied.status == SchedulePlanStatus.APPLIED
    assert task.planned_start_at is not None
