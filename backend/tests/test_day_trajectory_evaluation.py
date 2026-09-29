from datetime import date, datetime, time
from types import SimpleNamespace
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import User
from django.core.management.base import CommandError
from langchain_core.messages import AIMessage

from apps.agents.management.commands.evaluate_day_trajectory import (
    Command,
    _extract_interrupt_tool_names,
    compare_schedule_snapshots,
    trajectory_steps,
)
from apps.events.models import CalendarEvent, CalendarEventStatus
from apps.preferences.services import UserPreferenceService
from apps.tasks.models import Task


class RecordingAgent:
    def __init__(self) -> None:
        self.contexts: list[Any] = []
        self.inputs: list[Any] = []

    def invoke(
        self, state: dict[str, Any], *, config: dict[str, Any], context: Any
    ) -> dict[str, Any]:
        self.contexts.append(context)
        self.inputs.append(state["messages"])
        assert config["configurable"]["thread_id"] == context.conversation_id
        return {
            "messages": [
                *state["messages"],
                AIMessage(content="无需调整，保持原安排并继续观察。"),
            ]
        }


def test_synthetic_trajectory_has_ordered_whole_day_anchors_and_change_points() -> None:
    steps = trajectory_steps(date(2026, 10, 5))

    assert [step["id"] for step in steps] == [
        "08_initial_plan",
        "10_done",
        "11_30_overrun",
        "13_meeting_added",
        "15_task_cancelled",
        "16_urgent_added",
    ]
    assert [step["anchor"].hour for step in steps] == [8, 10, 11, 13, 15, 16]
    assert steps[2]["anchor"].minute == 30
    assert all(step["anchor"].tzinfo is not None for step in steps)
    assert [step["mutation"] for step in steps] == [
        None,
        "complete_inbox",
        "extend_minutes",
        "add_meeting",
        "cancel_records",
        "add_urgent",
    ]


@pytest.mark.parametrize(
    ("host", "name"),
    [("db.example.invalid", "time_agent_eval"), ("localhost", "time_agent_prod")],
)
def test_live_runner_rejects_remote_or_production_postgres_target(
    monkeypatch: pytest.MonkeyPatch, host: str, name: str
) -> None:
    monkeypatch.setattr(
        "apps.agents.management.commands.evaluate_day_trajectory.settings.DATABASES",
        {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "HOST": host,
                "NAME": name,
            }
        },
    )
    with pytest.raises(CommandError, match="production-named|local SQLite or loopback PostgreSQL"):
        Command._ensure_local_evaluation_database()


def test_schedule_churn_counts_changed_tasks_and_shift_distance() -> None:
    task_a, task_b = str(uuid4()), str(uuid4())
    zone = ZoneInfo("Asia/Shanghai")
    old = {
        task_a: [
            (
                datetime(2026, 10, 5, 9, 0, tzinfo=zone),
                datetime(2026, 10, 5, 10, 0, tzinfo=zone),
            )
        ],
        task_b: [
            (
                datetime(2026, 10, 5, 10, 0, tzinfo=zone),
                datetime(2026, 10, 5, 11, 0, tzinfo=zone),
            )
        ],
    }
    updated = {
        task_a: [
            (
                datetime(2026, 10, 5, 9, 30, tzinfo=zone),
                datetime(2026, 10, 5, 10, 30, tzinfo=zone),
            )
        ],
        task_b: old[task_b],
    }

    assert compare_schedule_snapshots(old, updated) == {
        "moved_task_count": 1,
        "total_shift_minutes": 30,
    }
    assert compare_schedule_snapshots(old, old) == {
        "moved_task_count": 0,
        "total_shift_minutes": 0,
    }


def test_deadline_and_worktime_metrics_detect_violations() -> None:
    task_id = str(uuid4())
    task = Task(
        id=task_id,
        title="synthetic",
        due_at=datetime(2026, 10, 5, 16, tzinfo=ZoneInfo("Asia/Shanghai")),
        estimated_minutes=90,
    )
    unplanned_id = str(uuid4())
    unplanned = Task(
        id=unplanned_id,
        title="unplanned",
        due_at=datetime(2026, 10, 5, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    slots = {
        task_id: [
            (
                datetime(2026, 10, 5, 16, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
                datetime(2026, 10, 5, 17, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
            )
        ]
    }
    event = CalendarEvent(
        start_at=datetime(2026, 10, 5, 16, 45, tzinfo=ZoneInfo("Asia/Shanghai")),
        end_at=datetime(2026, 10, 5, 17, 15, tzinfo=ZoneInfo("Asia/Shanghai")),
        status=CalendarEventStatus.CONFIRMED,
    )

    metrics = Command._preservation_metrics(
        slots=slots,
        tasks={task_id: task, unplanned_id: unplanned},
        day=date(2026, 10, 5),
        events=[event],
    )

    assert metrics["deadline_violation_count"] == 2
    assert metrics["deadline_preservation_rate"] == 0
    assert metrics["worktime_preference_violation_count"] == 1
    assert metrics["worktime_preference_preserved"] is False
    assert metrics["estimated_duration_mismatch_count"] == 1
    assert metrics["event_conflict_count"] == 1
    assert metrics["unplanned_active_task_count"] == 1


def test_hitl_extraction_logs_only_tool_names_and_seed_facts_use_application_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(id=1, username="temporary")
    task = Task(id=uuid4(), user=user, title="synthetic")
    observed: list[dict[str, object]] = []

    def fake_complete_task(**kwargs: Any) -> Task:
        observed.append(kwargs)
        return task

    monkeypatch.setattr(
        "apps.agents.management.commands.evaluate_day_trajectory.TaskService.complete_task",
        fake_complete_task,
    )
    anchor = datetime(2026, 10, 5, 10, tzinfo=ZoneInfo("Asia/Shanghai"))
    Command._apply_synthetic_mutation(
        "complete_inbox",
        user=user,
        task_map={"inbox": task},
        anchor=anchor,
    )
    assert observed == [
        {
            "task_id": task.pk,
            "user": user,
            "occurred_at": anchor.astimezone(ZoneInfo("UTC")),
            "origin": "evaluation",
        }
    ]

    interrupt = SimpleNamespace(
        value={
            "action_requests": [
                {"name": "reschedule_task", "args": {"task_id": "private-id"}},
            ]
        }
    )
    names = _extract_interrupt_tool_names(
        [interrupt],
        [
            AIMessage(
                content="",
                tool_calls=[{"id": "approval-1", "name": "reschedule_task", "args": {}}],
            )
        ],
    )
    assert names == ["reschedule_task"]


def test_duplicate_history_tool_calls_are_counted_once() -> None:
    previous = {"id": "call-1", "name": "get_planning_context", "args": {}}
    current = {"id": "call-2", "name": "propose_schedule_plan", "args": {}}
    message = AIMessage(content="", tool_calls=[previous])
    seen: set[str] = set()

    assert len(Command._safe_tool_calls([message], seen)) == 1
    assert Command._safe_tool_calls(
        [message, AIMessage(content="", tool_calls=[current])], seen
    ) == [{"name": "propose_schedule_plan", "status": "pending"}]


@pytest.mark.django_db
def test_trajectory_runner_reuses_history_and_applies_facts_through_services() -> None:
    user = User.objects.create_user(username=f"trajectory-test-{uuid4().hex}")
    UserPreferenceService.update_for_user(
        user,
        {
            "timezone": "Asia/Shanghai",
            "locale": "zh-CN",
            "workday_start": time(9),
            "workday_end": time(17),
        },
    )
    task_map = Command._seed_tasks(user, date(2026, 10, 5))
    agent = RecordingAgent()

    report = Command._run_trajectory(
        agent=agent,
        user=user,
        task_map=task_map,
        day=date(2026, 10, 5),
        request_ids=[],
    )

    assert report["step_count"] == 6
    assert report["approved_action_count"] == 0
    assert report["hitl_pending_count"] == 0
    assert [len(messages) for messages in agent.inputs] == [1, 3, 5, 7, 9, 11]
    assert len({context.conversation_id for context in agent.contexts}) == 1
    assert [
        context.current_datetime.astimezone(ZoneInfo("Asia/Shanghai")).hour
        for context in agent.contexts
    ] == [8, 10, 11, 13, 15, 16]
    assert [step["decision"] for step in report["steps"]] == ["keep_stable"] * 6
    task_map["inbox"].refresh_from_db()
    task_map["minutes"].refresh_from_db()
    task_map["records"].refresh_from_db()
    assert task_map["inbox"].status == "completed"
    assert task_map["minutes"].estimated_minutes == 90
    assert task_map["records"].status == "cancelled"
    assert "urgent" in task_map
    assert report["steps"][0]["tool_call_count"] == 0
    assert report["production_data_used"] is False
    user.delete()
