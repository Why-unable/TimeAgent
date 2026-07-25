from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model

from apps.reminders.models import ReminderTargetType
from apps.reminders.services import (
    CreateReminderCommand,
    ReminderService,
    UpdateReminderCommand,
)
from apps.tasks.services import CreateTaskCommand, TaskService

pytestmark = pytest.mark.django_db


def test_update_reminder_is_versioned_and_can_rebind_target() -> None:
    user = get_user_model().objects.create_user(username="reminder-editor")
    task = TaskService.create_task(CreateTaskCommand(user=user, title="Prepare report"))
    reminder = ReminderService.create_reminder(
        CreateReminderCommand(
            user=user,
            title="Submit report",
            trigger_at=datetime.now(UTC) + timedelta(days=2),
            timezone="Asia/Shanghai",
            deduplication_key="reminder-editor-1",
        )
    )

    updated = ReminderService.update_reminder(
        UpdateReminderCommand(
            user=user,
            reminder_id=reminder.pk,
            expected_version=1,
            changes={
                "title": "Submit final report",
                "target_type": ReminderTargetType.TASK,
                "target_id": task.pk,
            },
        )
    )

    assert updated.version == 2
    assert updated.target_id == task.pk
    with pytest.raises(ValueError, match="version conflict"):
        ReminderService.update_reminder(
            UpdateReminderCommand(
                user=user,
                reminder_id=reminder.pk,
                expected_version=1,
                changes={"title": "Stale write"},
            )
        )
