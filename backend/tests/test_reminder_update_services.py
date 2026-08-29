from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model

from apps.reminders.models import ReminderTargetType
from apps.reminders.services import (
    CreateReminderCommand,
    ReminderService,
    ReminderTriggerNotFutureError,
    UpdateReminderCommand,
)
from apps.tasks.services import CreateTaskCommand, TaskService

pytestmark = pytest.mark.django_db


def test_update_reminder_is_versioned_and_can_rebind_target() -> None:
    user = get_user_model().objects.create_user(username="reminder-editor")
    current_time = datetime.now(UTC)
    task = TaskService.create_task(CreateTaskCommand(user=user, title="Prepare report"))
    reminder = ReminderService.create_reminder(
        CreateReminderCommand(
            user=user,
            title="Submit report",
            trigger_at=current_time + timedelta(days=2),
            current_time=current_time,
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
            current_time=current_time,
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
                current_time=current_time,
            )
        )


def test_update_reminder_rejects_past_trigger_time() -> None:
    user = get_user_model().objects.create_user(username="past-reminder-editor")
    current_time = datetime.now(UTC)
    reminder = ReminderService.create_reminder(
        CreateReminderCommand(
            user=user,
            title="Future reminder",
            trigger_at=current_time + timedelta(days=1),
            current_time=current_time,
            timezone="Asia/Shanghai",
            deduplication_key="past-reminder-editor-1",
        )
    )

    with pytest.raises(ReminderTriggerNotFutureError, match="must be in the future"):
        ReminderService.update_reminder(
            UpdateReminderCommand(
                user=user,
                reminder_id=reminder.pk,
                expected_version=1,
                changes={"trigger_at": current_time - timedelta(minutes=1)},
                current_time=current_time,
            )
        )

    reminder.refresh_from_db()
    assert reminder.trigger_at == current_time + timedelta(days=1)
    assert reminder.version == 1
