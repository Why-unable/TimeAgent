from datetime import UTC, datetime, time
from unittest.mock import Mock

import pytest
from django.contrib.auth.models import User

from apps.briefings.scheduling import DailyBriefingScheduler
from apps.conversations.models import AgentRun, Conversation, ConversationKind
from apps.preferences.models import UserPreference

pytestmark = pytest.mark.django_db


def test_scheduler_finds_enabled_briefing_five_minutes_before_local_time() -> None:
    user = User.objects.create_user(username="scheduled-briefing")
    preference = UserPreference.objects.create(
        user=user,
        timezone="Asia/Shanghai",
        daily_briefing_enabled=True,
        briefing_time=time(8, 0),
    )
    now = datetime(2026, 7, 29, 23, 55, tzinfo=UTC)

    due = DailyBriefingScheduler.due(now=now)

    assert len(due) == 1
    assert due[0].preference_id == preference.pk
    assert due[0].target_date.isoformat() == "2026-07-30"
    assert due[0].generation_at == now
    assert due[0].delivery_at == datetime(2026, 7, 30, 0, 0, tzinfo=UTC)


def test_scheduler_ignores_users_who_did_not_enable_daily_briefings() -> None:
    user = User.objects.create_user(username="disabled-briefing")
    UserPreference.objects.create(
        user=user,
        timezone="Asia/Shanghai",
        daily_briefing_enabled=False,
        briefing_time=time(8, 0),
    )

    assert DailyBriefingScheduler.due(
        now=datetime(2026, 7, 29, 23, 55, tzinfo=UTC)
    ) == []


def test_scheduler_prepares_one_idempotent_scheduled_agent_run() -> None:
    user = User.objects.create_user(username="idempotent-briefing")
    UserPreference.objects.create(
        user=user,
        timezone="Asia/Shanghai",
        daily_briefing_enabled=True,
        briefing_time=time(8, 0),
    )
    due = DailyBriefingScheduler.due(
        now=datetime(2026, 7, 29, 23, 55, tzinfo=UTC)
    )[0]

    first, first_created = DailyBriefingScheduler.prepare(due)
    second, second_created = DailyBriefingScheduler.prepare(due)

    assert first_created is True
    assert second_created is False
    assert second.pk == first.pk
    assert first.trigger_type == "scheduled_briefing"
    assert first.synthetic_input is True
    assert first.trigger_payload["delivery_at"] == "2026-07-30T00:00:00+00:00"
    assert first.conversation.kind == ConversationKind.SCHEDULED_BRIEFING
    assert AgentRun.objects.count() == 1
    assert Conversation.objects.count() == 1


def test_beat_task_reserves_and_queues_each_due_run_once(monkeypatch: pytest.MonkeyPatch) -> None:
    user = User.objects.create_user(username="queued-briefing")
    UserPreference.objects.create(
        user=user,
        timezone="Asia/Shanghai",
        daily_briefing_enabled=True,
        briefing_time=time(8, 0),
    )
    now = datetime(2026, 7, 29, 23, 55, tzinfo=UTC)
    enqueue = Mock()
    monkeypatch.setattr("apps.briefings.tasks.timezone.now", lambda: now)
    monkeypatch.setattr("apps.briefings.tasks.execute_agent_run_task.apply_async", enqueue)

    from apps.briefings.tasks import schedule_due_daily_briefings

    assert schedule_due_daily_briefings.run() == 1
    assert schedule_due_daily_briefings.run() == 0
    assert enqueue.call_count == 1
    run = AgentRun.objects.get()
    assert run.execution_task_id
    assert enqueue.call_args.kwargs["task_id"] == run.execution_task_id
