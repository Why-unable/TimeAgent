from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth.models import User

from apps.events.services import CreateEventCommand, EventService
from apps.planning.models import AutomationPolicy, ScheduleChangeBatch
from apps.planning.tasks import dispatch_authorized_replans
from apps.tasks.services import CreateTaskCommand, TaskService

pytestmark = pytest.mark.django_db


def test_dispatcher_moves_only_explicitly_authorized_conflicting_task() -> None:
    user = User.objects.create_user("adaptive-dispatch")
    now = datetime(2026, 8, 24, 1, tzinfo=UTC)
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Authorized focus",
            estimated_minutes=30,
            planned_start_at=now + timedelta(hours=1),
            planned_end_at=now + timedelta(hours=1, minutes=30),
        )
    )
    untouched = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Not authorized",
            estimated_minutes=30,
            planned_start_at=now + timedelta(hours=2),
            planned_end_at=now + timedelta(hours=2, minutes=30),
        )
    )
    for start, title in (
        (now + timedelta(hours=1), "First conflict"),
        (now + timedelta(hours=2), "Second conflict"),
    ):
        EventService.create_event(
            CreateEventCommand(
                user=user,
                title=title,
                start_at=start,
                end_at=start + timedelta(minutes=30),
                timezone="Asia/Shanghai",
            )
        )
    AutomationPolicy.objects.create(
        user=user,
        name="Explicit focus maintenance",
        enabled=True,
        allow_task_reschedule=True,
        max_moves_per_run=2,
        requires_approval=False,
        authorized_task_ids=[str(task.pk)],
    )

    assert dispatch_authorized_replans(now) == 1
    task.refresh_from_db()
    untouched.refresh_from_db()
    assert task.planned_start_at != now + timedelta(hours=1)
    assert untouched.planned_start_at == now + timedelta(hours=2)
    assert ScheduleChangeBatch.objects.filter(user=user).count() == 1
    assert dispatch_authorized_replans(now) == 0
