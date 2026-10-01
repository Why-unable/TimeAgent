from datetime import UTC, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User

from apps.events.services import CreateEventCommand, EventService
from apps.planning.models import SchedulePlan
from apps.planning.schemas import TaskScheduleDecision
from apps.planning.services import PlanningService
from apps.preferences.services import UserPreferenceService
from apps.tasks.models import Task
from apps.tasks.services import CreateTaskCommand, TaskService

pytestmark = pytest.mark.django_db
SHANGHAI = ZoneInfo("Asia/Shanghai")
PLAN_NOW = datetime(2026, 10, 11, 0, tzinfo=UTC)
PLAN_START = datetime(2026, 10, 12, 0, tzinfo=UTC)
PLAN_END = datetime(2026, 11, 7, 0, tzinfo=UTC)


def local(day: int, hour: int = 9, minute: int = 0, *, month: int = 10) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=SHANGHAI)


def _user_and_preferences(username: str) -> User:
    user = get_user_model().objects.create_user(username=username)
    UserPreferenceService.update_for_user(
        user,
        {
            "timezone": "Asia/Shanghai",
            "workday_start": local(12, 9).time(),
            "workday_end": local(12, 18).time(),
        },
    )
    return user


def _create_tasks(user: User, definitions: list[tuple[str, int, int, int]]) -> list[Task]:
    tasks: list[Task] = []
    for title, duration, due_month, due_day in definitions:
        tasks.append(
            TaskService.create_task(
                CreateTaskCommand(
                    user=user,
                    title=title,
                    estimated_minutes=duration,
                    due_at=local(due_day, 18, month=due_month),
                )
            )
        )
    return tasks


def _plan_items_by_task(plan: SchedulePlan) -> dict[str, dict[str, Any]]:
    return {
        str(item["task_id"]): item for item in plan.items if item.get("kind") != "plan_evidence"
    }


def test_planning_context_is_one_bounded_read_for_tasks_events_and_preferences() -> None:
    user = _user_and_preferences("planning-context-user")
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Prepare release checklist",
            description="Review rollout steps",
            estimated_minutes=60,
            due_at=local(13, 17),
        )
    )
    event = EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Project review",
            start_at=local(13, 10),
            end_at=local(13, 11),
            timezone="Asia/Shanghai",
        )
    )

    context = PlanningService.get_planning_context(
        user=user,
        range_start=local(12).astimezone(UTC),
        range_end=local(14).astimezone(UTC),
    )
    context = cast(dict[str, Any], context)

    assert context["timezone"] == "Asia/Shanghai"
    assert context["workday_start"] == "09:00"
    assert context["workday_end"] == "18:00"
    context_tasks = cast(list[dict[str, Any]], context["tasks"])
    context_events = cast(list[dict[str, Any]], context["events"])
    assert context_tasks[0]["id"] == str(task.pk)
    assert context_tasks[0]["due_at_local"] == local(13, 17).isoformat()
    assert context_events[0]["id"] == str(event.pk)
    assert context_events[0]["start_at_local"] == local(13, 10).isoformat()
    assert context["tasks_truncated"] is False


def test_free_slot_mode_returns_availability_without_planning_facts() -> None:
    user = _user_and_preferences("free-slot-context-user")
    TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Private task title should not be needed",
            estimated_minutes=60,
        )
    )
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Private event title should not be needed",
            start_at=local(12, 9).astimezone(UTC),
            end_at=local(12, 10).astimezone(UTC),
            timezone="Asia/Shanghai",
        )
    )

    result = PlanningService.get_planning_context(
        user=user,
        range_start=local(12).astimezone(UTC),
        range_end=local(13).astimezone(UTC),
        mode="free_slots",
        duration_minutes=60,
        max_free_slots=2,
        reference_start_at=local(12, 11),
        reference_end_at=local(12, 12),
    )
    result = cast(dict[str, Any], result)

    assert result["timezone"] == "Asia/Shanghai"
    free_slots = cast(list[dict[str, Any]], result["free_slots"])
    assert len(free_slots) == 2
    local_start = datetime.fromisoformat(str(free_slots[0]["start_at_local"]))
    utc_start = datetime.fromisoformat(str(free_slots[0]["start_at"]))
    assert local_start.utcoffset() is not None
    assert local_start.utcoffset() == timedelta(hours=8)
    assert local_start.astimezone(UTC) == utc_start
    assert free_slots[0]["movement_minutes"] == 0
    assert local_start == local(12, 11)
    assert "tasks" not in result
    assert "events" not in result
    assert "planning_rules" not in result


def test_exact_start_decision_places_task_at_the_requested_instant() -> None:
    user = _user_and_preferences("exact-start-plan")
    task = _create_tasks(user, [("Exact start task", 30, 10, 13)])[0]
    target = local(12, 10, 45)

    plan = PlanningService.propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=local(12, 9).astimezone(UTC),
        range_end=local(13, 18).astimezone(UTC),
        strategy="plan_tasks_only",
        task_decisions=[TaskScheduleDecision(task_id=task.pk, exact_start_at=target)],
        now=local(12, 8).astimezone(UTC),
    )

    item = _plan_items_by_task(plan)[str(task.pk)]
    assert item["state"] == "placed"
    assert datetime.fromisoformat(str(item["start_at"])) == target.astimezone(UTC)
    assert datetime.fromisoformat(str(item["end_at"])) == target.astimezone(UTC) + timedelta(
        minutes=30
    )
    assert PlanningService.validate_schedule_plan(
        user=user,
        plan_id=plan.pk,
        expected_version=plan.version,
        now=local(12, 8).astimezone(UTC),
    ).is_valid


def test_exact_start_decision_does_not_shift_when_requested_slot_conflicts() -> None:
    user = _user_and_preferences("exact-start-conflict")
    task = _create_tasks(user, [("Conflicting exact start task", 30, 10, 13)])[0]
    target = local(12, 10, 45)
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Exact requested time is busy",
            start_at=target.astimezone(UTC),
            end_at=(target + timedelta(minutes=30)).astimezone(UTC),
            timezone="Asia/Shanghai",
        )
    )

    plan = PlanningService.propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=local(12, 9).astimezone(UTC),
        range_end=local(13, 18).astimezone(UTC),
        strategy="plan_tasks_only",
        task_decisions=[TaskScheduleDecision(task_id=task.pk, exact_start_at=target)],
        now=local(12, 8).astimezone(UTC),
    )

    item = _plan_items_by_task(plan)[str(task.pk)]
    assert item["state"] == "unplaced"
    assert item["reason_codes"] == ["exact_start_unavailable"]


def test_reference_ranked_free_slots_include_nearest_candidate_across_long_range() -> None:
    user = _user_and_preferences("nearest-free-slot-across-range")
    reference_start = local(12, 13)
    reference_end = local(12, 15)
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Analyze customer usage",
            priority="high",
            estimated_minutes=120,
            due_at=local(15, 17),
            planned_start_at=reference_start,
            planned_end_at=reference_end,
        )
    )
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Customer review",
            start_at=local(12, 13),
            end_at=local(12, 16),
            timezone="Asia/Shanghai",
        )
    )

    result = PlanningService.get_planning_context(
        user=user,
        range_start=datetime(2026, 10, 5, 0, tzinfo=SHANGHAI),
        range_end=local(15, 17),
        mode="free_slots",
        duration_minutes=120,
        allowed_weekdays=[0, 1, 2, 3, 4],
        reference_start_at=reference_start,
        reference_end_at=reference_end,
    )
    slots = cast(list[dict[str, Any]], result["free_slots"])

    assert slots[0]["start_at_local"] == local(12, 11).isoformat()
    assert slots[0]["end_at_local"] == local(12, 13).isoformat()
    assert slots[0]["movement_minutes"] == 240
    assert Task.objects.get(pk=task.pk).planned_start_at == reference_start.astimezone(UTC)


def test_task_scoped_free_slots_derive_duration_reference_deadline_and_version() -> None:
    user = _user_and_preferences("task-scoped-free-slots")
    original_start = local(12, 13)
    original_end = local(12, 15)
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Analyze customer usage",
            estimated_minutes=120,
            due_at=local(15, 17),
            planned_start_at=original_start,
            planned_end_at=original_end,
        )
    )
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Customer review",
            start_at=local(12, 13),
            end_at=local(12, 16),
            timezone="Asia/Shanghai",
        )
    )

    result = PlanningService.get_planning_context(
        user=user,
        range_start=datetime(2026, 10, 5, 0, tzinfo=SHANGHAI),
        range_end=local(31, 17),
        mode="free_slots",
        duration_minutes=180,
        task_id=task.pk,
        allowed_weekdays=[0, 1, 2, 3, 4],
        reference_start_at=local(12, 13),
        reference_end_at=local(12, 16),
    )
    slots = cast(list[dict[str, Any]], result["free_slots"])
    task_context = cast(dict[str, Any], result["task"])

    assert result["duration_minutes"] == 120
    assert result["range_end_local"] == local(15, 17).isoformat()
    assert result["reference_start_at_local"] == original_start.isoformat()
    assert result["reference_end_at_local"] == original_end.isoformat()
    assert task_context["id"] == str(task.pk)
    assert task_context["version"] == task.version
    assert slots[0]["start_at_local"] == local(12, 11).isoformat()
    assert slots[0]["end_at_local"] == local(12, 13).isoformat()
    assert slots[0]["movement_minutes"] == 240


def test_free_slot_mode_requires_duration_and_valid_weekday_values() -> None:
    user = _user_and_preferences("free-slot-validation-user")

    with pytest.raises(ValueError, match="duration_minutes is required"):
        PlanningService.get_planning_context(
            user=user,
            range_start=PLAN_START,
            range_end=PLAN_END,
            mode="free_slots",
        )
    with pytest.raises(ValueError, match="allowed_weekdays"):
        PlanningService.get_planning_context(
            user=user,
            range_start=PLAN_START,
            range_end=PLAN_END,
            mode="free_slots",
            duration_minutes=60,
            allowed_weekdays=[7],
        )


def test_agent_guided_four_week_training_decisions_improve_temporal_spread() -> None:
    user = _user_and_preferences("agent-guided-training")
    tasks = _create_tasks(
        user,
        [
            ("第一周：轻松跑和训练记录", 60, 10, 16),
            ("第一周：核心力量与拉伸", 45, 10, 19),
            ("第二周：间歇跑训练", 75, 10, 23),
            ("第二周：检查跑鞋和装备", 45, 10, 26),
            ("第三周：节奏跑并记录配速", 75, 10, 30),
            ("第三周：补水和恢复计划复核", 45, 11, 2),
            ("第四周：赛前轻量测试跑", 60, 11, 5),
            ("比赛日路线与交通确认", 45, 11, 6),
        ],
    )
    baseline = PlanningService.propose_schedule_plan(
        user=user,
        task_ids=[task.pk for task in tasks],
        range_start=PLAN_START,
        range_end=PLAN_END,
        strategy="plan_tasks_only",
        now=PLAN_NOW,
    )
    baseline_items = _plan_items_by_task(baseline)
    baseline_weeks = {
        datetime.fromisoformat(str(item["start_at"])).astimezone(SHANGHAI).isocalendar().week
        for item in baseline_items.values()
        if item.get("state") == "placed"
    }

    phase_dates = [12, 19, 26]
    task_decisions: list[TaskScheduleDecision] = []
    for index, task in enumerate(tasks):
        phase = index // 2
        month = 11 if phase == 3 else 10
        first_day = 2 if phase == 3 else phase_dates[phase]
        target_day = [12, 15, 20, 22, 27, 29, 2, 4][index]
        target_month = 11 if target_day < 12 and index >= 6 else 10
        predecessors = (
            [tasks[index - 2].pk, tasks[index - 1].pk] if phase > 0 and index % 2 == 0 else []
        )
        task_decisions.append(
            TaskScheduleDecision(
                task_id=task.pk,
                earliest_start_at=local(first_day, 9, month=month),
                preferred_start_at=local(target_day, 9, 30, month=target_month),
                predecessor_task_ids=predecessors,
                minimum_gap_days=5 if predecessors else 0,
                rationale=f"安排在第 {phase + 1} 周训练阶段。",
            )
        )
    guided = PlanningService.propose_schedule_plan(
        user=user,
        task_ids=[task.pk for task in tasks],
        range_start=PLAN_START,
        range_end=PLAN_END,
        strategy="plan_tasks_only",
        task_decisions=task_decisions,
        now=PLAN_NOW,
    )
    guided_items = _plan_items_by_task(guided)
    guided_weeks = {
        datetime.fromisoformat(str(item["start_at"])).astimezone(SHANGHAI).isocalendar().week
        for item in guided_items.values()
        if item.get("state") == "placed"
    }
    phase_week_by_title = {
        "第一周": 42,
        "第二周": 43,
        "第三周": 44,
        "第四周": 45,
        "比赛日": 45,
    }

    assert len(baseline_weeks) == 1
    assert len(guided_weeks) == 4
    assert all(item.get("state") == "placed" for item in guided_items.values())

    def task_phase_week(task: Task) -> tuple[int, int]:
        phase = next(prefix for prefix in phase_week_by_title if task.title.startswith(prefix))
        item = guided_items[str(task.pk)]
        actual_week = (
            datetime.fromisoformat(str(item["start_at"])).astimezone(SHANGHAI).isocalendar().week
        )
        return actual_week, phase_week_by_title[phase]

    assert all(
        actual_week == expected_week
        for actual_week, expected_week in (task_phase_week(task) for task in tasks)
    )
    evidence = next(
        item["evidence"] for item in guided.items if item.get("kind") == "plan_evidence"
    )
    assert evidence["planner_version"] == "v3_agent_guided"
    assert evidence["creation_validation"] == {"valid": True, "reason_codes": []}


def test_agent_guided_exam_plan_enforces_learning_sequence_and_spacing() -> None:
    user = _user_and_preferences("agent-guided-exam")
    tasks = _create_tasks(
        user,
        [
            ("阅读认证考试范围并列知识点", 120, 10, 16),
            ("复习法规模块并完成章节题", 150, 10, 22),
            ("复习流程模块并整理易错点", 150, 10, 27),
            ("完成第一套限时模拟卷", 180, 10, 30),
            ("按模拟错题补强薄弱章节", 150, 11, 3),
            ("准备考试材料并确认考场交通", 60, 11, 5),
            ("完成第二套模拟卷并复盘", 180, 11, 6),
        ],
    )
    baseline = PlanningService.propose_schedule_plan(
        user=user,
        task_ids=[task.pk for task in tasks],
        range_start=PLAN_START,
        range_end=PLAN_END,
        strategy="plan_tasks_only",
        now=PLAN_NOW,
    )
    baseline_items = _plan_items_by_task(baseline)
    baseline_dates = {
        datetime.fromisoformat(str(item["start_at"])).astimezone(SHANGHAI).date()
        for item in baseline_items.values()
        if item.get("state") == "placed"
    }
    (syllabus, law, process, mock_one, remediation, materials, mock_two) = tasks
    decisions = [
        TaskScheduleDecision(
            task_id=syllabus.pk,
            preferred_start_at=local(12, 9, 30),
            rationale="先建立考试范围清单。",
        ),
        TaskScheduleDecision(
            task_id=law.pk,
            earliest_start_at=local(13, 9),
            preferred_start_at=local(15, 9, 30),
            predecessor_task_ids=[syllabus.pk],
            minimum_gap_days=1,
            rationale="先完成知识范围梳理，再进入法规模块。",
        ),
        TaskScheduleDecision(
            task_id=process.pk,
            earliest_start_at=local(15, 9),
            preferred_start_at=local(20, 9, 30),
            predecessor_task_ids=[syllabus.pk],
            minimum_gap_days=1,
            rationale="先完成知识范围梳理，再进入流程模块。",
        ),
        TaskScheduleDecision(
            task_id=mock_one.pk,
            earliest_start_at=local(26, 9),
            preferred_start_at=local(27, 9, 30),
            predecessor_task_ids=[law.pk, process.pk],
            minimum_gap_days=1,
            rationale="两门核心模块完成后再进行第一次模拟考试。",
        ),
        TaskScheduleDecision(
            task_id=remediation.pk,
            earliest_start_at=local(27, 9),
            preferred_start_at=local(29, 9, 30),
            predecessor_task_ids=[mock_one.pk],
            minimum_gap_days=1,
            rationale="模拟考试后根据错题进行针对性补强。",
        ),
        TaskScheduleDecision(
            task_id=materials.pk,
            earliest_start_at=local(2, 9, month=11),
            preferred_start_at=local(4, 9, 30, month=11),
            rationale="考前几天集中确认考试材料和交通。",
        ),
        TaskScheduleDecision(
            task_id=mock_two.pk,
            earliest_start_at=local(2, 9, month=11),
            preferred_start_at=local(3, 9, 30, month=11),
            predecessor_task_ids=[remediation.pk],
            minimum_gap_days=1,
            rationale="错题补强后再进行第二套模拟考试。",
        ),
    ]
    guided = PlanningService.propose_schedule_plan(
        user=user,
        task_ids=[task.pk for task in tasks],
        range_start=PLAN_START,
        range_end=PLAN_END,
        strategy="plan_tasks_only",
        task_decisions=decisions,
        now=PLAN_NOW,
    )
    guided_items = _plan_items_by_task(guided)
    guided_dates = {
        datetime.fromisoformat(str(item["start_at"])).astimezone(SHANGHAI).date()
        for item in guided_items.values()
        if item.get("state") == "placed"
    }

    assert len(baseline_dates) <= 3
    assert all(item.get("state") == "placed" for item in guided_items.values())

    def start(task: Task) -> datetime:
        return datetime.fromisoformat(str(guided_items[str(task.pk)]["start_at"]))

    def end(task: Task) -> datetime:
        return datetime.fromisoformat(str(guided_items[str(task.pk)]["end_at"]))

    one_day = timedelta(days=1)
    assert start(law) >= end(syllabus) + one_day
    assert start(process) >= end(syllabus) + one_day
    assert start(mock_one) >= end(law) + one_day
    assert start(mock_one) >= end(process) + one_day
    assert start(remediation) >= end(mock_one) + one_day
    assert start(mock_two) >= end(remediation) + one_day
    assert start(mock_two) > start(mock_one)
    assert len(guided_dates) >= 6
    assert (max(guided_dates) - min(guided_dates)).days >= 20


def test_cyclic_agent_dependencies_are_rejected_before_a_draft_is_created() -> None:
    user = _user_and_preferences("agent-guided-cycle")
    first, second = _create_tasks(
        user,
        [("Write outline", 60, 10, 23), ("Review outline", 60, 10, 23)],
    )

    with pytest.raises(ValueError, match="dependency cycle"):
        PlanningService.propose_schedule_plan(
            user=user,
            task_ids=[first.pk, second.pk],
            range_start=PLAN_START,
            range_end=PLAN_END,
            strategy="plan_tasks_only",
            task_decisions=[
                TaskScheduleDecision(task_id=first.pk, predecessor_task_ids=[second.pk]),
                TaskScheduleDecision(task_id=second.pk, predecessor_task_ids=[first.pk]),
            ],
            now=PLAN_NOW,
        )
    assert not SchedulePlan.objects.filter(user=user).exists()
