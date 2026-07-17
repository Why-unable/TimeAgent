from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.test import Client

from apps.events.models import CalendarEventStatus
from apps.events.services import CreateEventCommand, EventService
from apps.preferences.services import UserPreferenceService
from apps.reminders.services import CreateReminderCommand, ReminderService
from apps.tasks.services import CreateTaskCommand, TaskService
from apps.today.schemas import ScheduleItemKind
from apps.today.services import TodayService

pytestmark = pytest.mark.django_db

TODAY_URL = "/api/v1/today/"
SHANGHAI = ZoneInfo("Asia/Shanghai")


def create_user(username: str = "today-user") -> User:
    return get_user_model().objects.create_user(username=username)


def local_datetime(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, day, hour, minute, tzinfo=SHANGHAI)


def create_event(
    user: User,
    title: str,
    start_at: datetime,
    end_at: datetime,
    *,
    status: CalendarEventStatus | str = CalendarEventStatus.CONFIRMED,
) -> None:
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title=title,
            start_at=start_at,
            end_at=end_at,
            timezone="Asia/Shanghai",
            status=status,
        )
    )


def test_today_summary_uses_user_timezone_and_builds_all_buckets() -> None:
    user = create_user()
    other = create_user("today-other")
    current_at = local_datetime(20, 12)
    create_event(user, "上午复盘", local_datetime(20, 9), local_datetime(20, 10))
    create_event(user, "下一个会议", local_datetime(20, 13), local_datetime(20, 14))
    create_event(
        user,
        "已取消会议",
        local_datetime(20, 15),
        local_datetime(20, 16),
        status=CalendarEventStatus.CANCELLED,
    )
    create_event(other, "其他用户会议", local_datetime(20, 13), local_datetime(20, 14))

    planned = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="计划写作",
            planned_start_at=local_datetime(20, 13, 30),
            planned_end_at=local_datetime(20, 14, 30),
        )
    )
    due = TaskService.create_task(
        CreateTaskCommand(user=user, title="今日截止", due_at=local_datetime(20, 18))
    )
    overdue = TaskService.create_task(
        CreateTaskCommand(user=user, title="历史逾期", due_at=local_datetime(19, 18))
    )
    completed = TaskService.create_task(
        CreateTaskCommand(user=user, title="已完成旧任务", due_at=local_datetime(19, 17))
    )
    TaskService.complete_task(task_id=completed.id, user=user, occurred_at=current_at)
    ReminderService.create_reminder(
        CreateReminderCommand(
            user=user,
            title="下午提醒",
            trigger_at=local_datetime(20, 15),
            timezone="Asia/Shanghai",
            deduplication_key="today-afternoon",
        )
    )

    summary = TodayService.get_summary(user=user, current_at=current_at)

    assert summary.date.isoformat() == "2026-07-20"
    assert summary.timezone == "Asia/Shanghai"
    assert summary.day_start_at == datetime(2026, 7, 19, 16, tzinfo=UTC)
    assert summary.day_end_at == datetime(2026, 7, 20, 16, tzinfo=UTC)
    assert [event.title for event in summary.events] == ["上午复盘", "下一个会议"]
    assert summary.planned_tasks == [planned]
    assert summary.due_tasks == [due]
    assert summary.overdue_tasks == [overdue]
    assert [reminder.title for reminder in summary.pending_reminders] == ["下午提醒"]
    assert summary.next_event is not None
    assert summary.next_event.title == "下一个会议"
    assert summary.minutes_until_next_event == 60
    assert len(summary.conflicts) == 1
    conflict = summary.conflicts[0]
    assert {conflict.first.kind, conflict.second.kind} == {
        ScheduleItemKind.EVENT,
        ScheduleItemKind.TASK,
    }
    assert conflict.overlap_start_at == local_datetime(20, 13, 30).astimezone(UTC)
    assert conflict.overlap_end_at == local_datetime(20, 14).astimezone(UTC)


def test_today_summary_respects_dst_day_length() -> None:
    user = create_user()
    UserPreferenceService.update_for_user(user, {"timezone": "America/New_York"})
    current_at = datetime(2026, 3, 8, 12, tzinfo=UTC)

    summary = TodayService.get_summary(user=user, current_at=current_at)

    assert summary.date.isoformat() == "2026-03-08"
    assert summary.day_start_at == datetime(2026, 3, 8, 5, tzinfo=UTC)
    assert summary.day_end_at == datetime(2026, 3, 9, 4, tzinfo=UTC)
    assert summary.day_end_at - summary.day_start_at == timedelta(hours=23)


def test_today_api_requires_authentication_and_returns_structured_summary() -> None:
    anonymous_response = Client().get(TODAY_URL)
    assert anonymous_response.status_code in (401, 403)

    user = create_user()
    client = Client()
    client.force_login(user)
    create_event(user, "接口会议", local_datetime(20, 13), local_datetime(20, 14))

    with patch("apps.today.services.timezone.now", return_value=local_datetime(20, 12)):
        response = client.get(TODAY_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-07-20"
    assert body["timezone"] == "Asia/Shanghai"
    assert [event["title"] for event in body["events"]] == ["接口会议"]
    assert body["planned_tasks"] == []
    assert body["due_tasks"] == []
    assert body["overdue_tasks"] == []
    assert body["pending_reminders"] == []
    assert body["conflicts"] == []
    assert body["next_event"]["title"] == "接口会议"
    assert body["minutes_until_next_event"] == 60
