from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model

from apps.events.services import CreateEventCommand, EventService
from apps.planning.models import SchedulePlanStatus
from apps.planning.schemas import DailyAvailabilityWindow
from apps.planning.services import PlanningService
from apps.preferences.services import UserPreferenceService
from apps.tasks.services import CreateTaskCommand, TaskService

pytestmark = pytest.mark.django_db
SHANGHAI = ZoneInfo("Asia/Shanghai")


@pytest.fixture(autouse=True)
def freeze_planning_service_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_now = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr("apps.planning.services.timezone.now", lambda: fixed_now)


def _propose_schedule_plan(**kwargs):
    kwargs.setdefault("now", kwargs["range_start"])
    return PlanningService.propose_schedule_plan(**kwargs)


def test_free_slot_context_excludes_times_before_the_injected_run_anchor() -> None:
    user = get_user_model().objects.create_user(username="free-slots-run-anchor")
    UserPreferenceService.update_for_user(user, {"timezone": "UTC"})
    range_start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    range_end = datetime(2026, 8, 24, 17, tzinfo=UTC)
    run_anchor = datetime(2026, 8, 24, 13, tzinfo=UTC)

    context = PlanningService.get_planning_context(
        user=user,
        range_start=range_start,
        range_end=range_end,
        mode="free_slots",
        duration_minutes=30,
        not_before=run_anchor,
    )

    assert context["range_start"] == run_anchor.isoformat()
    free_slots = context["free_slots"]
    assert isinstance(free_slots, list)
    assert free_slots
    assert all(datetime.fromisoformat(str(slot["start_at"])) >= run_anchor for slot in free_slots)


def test_free_slot_context_applies_date_bounded_worktime_overrides() -> None:
    user = get_user_model().objects.create_user(username="free-slots-daily-override")
    UserPreferenceService.update_for_user(
        user,
        {
            "timezone": "UTC",
            "workday_start": time(9),
            "workday_end": time(17),
        },
    )
    context = PlanningService.get_planning_context(
        user=user,
        range_start=datetime(2026, 8, 24, tzinfo=UTC),
        range_end=datetime(2026, 8, 26, 23, 59, tzinfo=UTC),
        mode="free_slots",
        duration_minutes=60,
        one_slot_per_local_date=True,
        max_free_slots=10,
        daily_worktime_overrides=[
            DailyAvailabilityWindow(
                start_date=datetime(2026, 8, 25).date(),
                end_date=datetime(2026, 8, 25).date(),
                daily_start=time(14),
                daily_end=time(17),
            )
        ],
    )

    free_slots = context["free_slots"]
    assert isinstance(free_slots, list)
    slots_by_day: dict[str, list[dict[str, object]]] = {}
    for slot in free_slots:
        local_start = datetime.fromisoformat(str(slot["start_at_local"]))
        local_end = datetime.fromisoformat(str(slot["end_at_local"]))
        slots_by_day.setdefault(local_start.date().isoformat(), []).append(slot)
        if local_start.date().isoformat() == "2026-08-25":
            assert local_start.time() >= time(14)
            assert local_end.time() <= time(17)
    assert len(free_slots) == 3
    assert len(slots_by_day) == 3
    assert datetime.fromisoformat(
        str(slots_by_day["2026-08-24"][0]["start_at_local"])
    ).time() == time(9)
    assert datetime.fromisoformat(
        str(slots_by_day["2026-08-25"][0]["start_at_local"])
    ).time() == time(14)


def test_context_mode_rejects_free_slot_constraints() -> None:
    user = get_user_model().objects.create_user(username="context-rejects-free-slot-args")
    with pytest.raises(ValueError, match="free-slot options"):
        PlanningService.get_planning_context(
            user=user,
            range_start=datetime(2026, 8, 24, tzinfo=UTC),
            range_end=datetime(2026, 8, 26, tzinfo=UTC),
            mode="context",
            daily_worktime_overrides=[
                DailyAvailabilityWindow(
                    start_date=datetime(2026, 8, 25).date(),
                    end_date=datetime(2026, 8, 25).date(),
                    daily_start=time(14),
                    daily_end=time(17),
                )
            ],
        )


@pytest.mark.parametrize(
    ("durations", "daily_limit"),
    [((30, 45, 60), 180), ((60, 60, 60), 120), ((75, 75, 75), 150)],
)
def test_generated_plan_satisfies_core_interval_and_task_count_invariants(
    durations: tuple[int, ...], daily_limit: int
) -> None:
    user = get_user_model().objects.create_user(
        username=f"invariants-{daily_limit}-{sum(durations)}"
    )
    UserPreferenceService.update_for_user(
        user,
        {
            "timezone": "UTC",
            "workday_start": time(9),
            "workday_end": time(17),
        },
    )
    start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    event_start = start + timedelta(hours=2)
    event_end = event_start + timedelta(hours=1)
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Invariant test meeting",
            start_at=event_start,
            end_at=event_end,
            timezone="UTC",
        )
    )
    tasks = [
        TaskService.create_task(
            CreateTaskCommand(
                user=user,
                title=f"Invariant task {index}",
                estimated_minutes=duration,
            )
        )
        for index, duration in enumerate(durations)
    ]

    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk for task in tasks],
        range_start=start,
        range_end=start + timedelta(hours=8),
        strategy="plan_tasks_only",
        max_daily_minutes=daily_limit,
    )
    task_items = [item for item in plan.items if item.get("task_id")]
    placed = [item for item in task_items if item.get("state") == "placed"]
    intervals = sorted(
        [
            (
                str(item["task_id"]),
                datetime.fromisoformat(str(item["start_at"])),
                datetime.fromisoformat(str(item["end_at"])),
            )
            for item in placed
        ],
        key=lambda interval: interval[1],
    )
    evidence = next(item["evidence"] for item in plan.items if item.get("kind") == "plan_evidence")

    for task in tasks:
        segments = [item for item in placed if item.get("task_id") == str(task.pk)]
        if segments:
            assert (
                sum(
                    round(
                        (
                            datetime.fromisoformat(str(item["end_at"]))
                            - datetime.fromisoformat(str(item["start_at"]))
                        ).total_seconds()
                        / 60
                    )
                    for item in segments
                )
                == task.estimated_minutes
            )
    for index, (_task_id, interval_start, interval_end) in enumerate(intervals):
        assert interval_start >= start
        assert interval_end <= start + timedelta(hours=8)
        assert not (interval_start < event_end and interval_end > event_start)
        if index:
            assert intervals[index - 1][2] <= interval_start
    daily_task_minutes = sum(
        round((interval_end - interval_start).total_seconds() / 60)
        for _, interval_start, interval_end in intervals
    )
    assert daily_task_minutes <= daily_limit
    assert evidence["placed_count"] + evidence["unplaced_count"] == len(tasks)
    assert evidence["placed_segment_count"] == len(placed)
    assert evidence["segment_count"] == len(task_items)


def test_propose_then_apply_task_schedule_plan() -> None:
    user = get_user_model().objects.create_user(username="plan-user")
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Write outline", estimated_minutes=30)
    )
    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=datetime(2026, 7, 27, 1, tzinfo=UTC),
        range_end=datetime(2026, 7, 28, 1, tzinfo=UTC),
        strategy="plan_tasks_only",
        now=datetime(2026, 7, 27, 0, tzinfo=UTC),
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


def test_plan_never_places_work_before_runtime_anchor() -> None:
    user = get_user_model().objects.create_user(username="plan-now-boundary")
    UserPreferenceService.update_for_user(
        user,
        {
            "timezone": "Asia/Shanghai",
            "workday_start": time(9),
            "workday_end": time(17),
        },
    )
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Finish review", estimated_minutes=60)
    )
    now = datetime(2026, 8, 24, 6, 30, tzinfo=UTC)  # 14:30 local

    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=datetime(2026, 8, 23, 16, tzinfo=UTC),  # 00:00 local
        range_end=datetime(2026, 8, 25, 16, tzinfo=UTC),
        strategy="plan_tasks_only",
        now=now,
    )

    item = next(item for item in plan.items if item.get("task_id"))
    assert item["state"] == "placed"
    start_at = datetime.fromisoformat(str(item["start_at"]))
    assert start_at >= now
    assert start_at.astimezone(SHANGHAI).time() == time(14, 30)


def test_applying_a_plan_after_its_start_time_invalidates_it() -> None:
    user = get_user_model().objects.create_user(username="stale-plan-now-boundary")
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Send review", estimated_minutes=30)
    )
    now = datetime(2026, 8, 24, 6, 30, tzinfo=UTC)
    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=datetime(2026, 8, 24, 0, tzinfo=UTC),
        range_end=datetime(2026, 8, 25, 0, tzinfo=UTC),
        strategy="plan_tasks_only",
        now=now,
    )
    item = next(item for item in plan.items if item.get("task_id"))
    start_at = datetime.fromisoformat(str(item["start_at"]))

    with pytest.raises(ValueError, match="schedule_in_past"):
        PlanningService.apply_schedule_plan(
            user=user,
            plan_id=plan.pk,
            expected_version=plan.version,
            now=start_at + timedelta(minutes=1),
        )

    plan.refresh_from_db()
    assert plan.status == SchedulePlanStatus.INVALIDATED
    task.refresh_from_db()
    assert task.planned_start_at is None


def test_weekend_schedule_plan_uses_the_same_saved_constraint_for_validation() -> None:
    user = get_user_model().objects.create_user(username="weekend-plan-user")
    UserPreferenceService.update_for_user(
        user,
        {
            "timezone": "Asia/Shanghai",
            "workday_start": time(9),
            "workday_end": time(17),
        },
    )
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Weekend project work",
            estimated_minutes=30,
            due_at=datetime(2026, 11, 8, 17, tzinfo=SHANGHAI),
        )
    )
    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=datetime(2026, 11, 7, 9, tzinfo=SHANGHAI),
        range_end=datetime(2026, 11, 8, 17, tzinfo=SHANGHAI),
        strategy="plan_tasks_only",
        allowed_weekdays=(5, 6),
    )

    item = next(item for item in plan.items if item.get("task_id") == str(task.pk))
    validation = PlanningService.validate_schedule_plan(
        user=user,
        plan_id=plan.pk,
        expected_version=plan.version,
    )

    assert item["state"] == "placed"
    assert datetime.fromisoformat(str(item["start_at"])).astimezone(SHANGHAI).weekday() == 5
    assert plan.constraints_snapshot["allowed_weekdays"] == [5, 6]
    assert validation.is_valid is True


def test_schedule_plan_persists_and_revalidates_temporary_daily_windows() -> None:
    user = get_user_model().objects.create_user(username="temporary-window-plan-user")
    UserPreferenceService.update_for_user(
        user,
        {
            "timezone": "Asia/Shanghai",
            "workday_start": time(9),
            "workday_end": time(17),
        },
    )
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Prepare project update",
            estimated_minutes=60,
            due_at=datetime(2026, 10, 9, 17, tzinfo=SHANGHAI),
        )
    )
    window = DailyAvailabilityWindow(
        start_date=datetime(2026, 10, 8).date(),
        end_date=datetime(2026, 10, 9).date(),
        daily_start=time(10, 30),
        daily_end=time(17),
    )
    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=datetime(2026, 10, 8, 0, tzinfo=SHANGHAI),
        range_end=datetime(2026, 10, 10, 0, tzinfo=SHANGHAI),
        strategy="plan_tasks_only",
        daily_worktime_overrides=[window],
    )
    item = next(item for item in plan.items if item.get("task_id") == str(task.pk))
    validation = PlanningService.validate_schedule_plan(
        user=user,
        plan_id=plan.pk,
        expected_version=plan.version,
    )

    assert datetime.fromisoformat(str(item["start_at"])).astimezone(SHANGHAI).time() == time(10, 30)
    assert plan.constraints_snapshot["daily_worktime_overrides"] == [
        {
            "start_date": "2026-10-08",
            "end_date": "2026-10-09",
            "daily_start": "10:30:00",
            "daily_end": "17:00:00",
        }
    ]
    assert validation.is_valid is True

    item["start_at"] = "2026-10-08T09:00:00+08:00"
    item["end_at"] = "2026-10-08T10:00:00+08:00"
    item["reserved_start_at"] = item["start_at"]
    item["reserved_end_at"] = item["end_at"]
    plan.items = [item if row.get("task_id") == str(task.pk) else row for row in plan.items]
    plan.save(update_fields=["items"])
    invalid = PlanningService.validate_schedule_plan(
        user=user,
        plan_id=plan.pk,
        expected_version=plan.version,
    )

    assert invalid.is_valid is False
    assert "work_hours_violation" in invalid.reason_codes


def test_schedule_plan_enforces_and_revalidates_daily_task_minutes() -> None:
    user = get_user_model().objects.create_user(username="daily-cap-plan-user")
    UserPreferenceService.update_for_user(
        user,
        {
            "timezone": "Asia/Shanghai",
            "workday_start": time(9),
            "workday_end": time(17),
        },
    )
    tasks = [
        TaskService.create_task(
            CreateTaskCommand(user=user, title=f"Focus task {index}", estimated_minutes=90)
        )
        for index in range(2)
    ]
    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk for task in tasks],
        range_start=datetime(2026, 7, 27, 0, tzinfo=SHANGHAI),
        range_end=datetime(2026, 7, 29, 0, tzinfo=SHANGHAI),
        strategy="plan_tasks_only",
        max_daily_minutes=120,
    )
    placed = [item for item in plan.items if item.get("state") == "placed"]
    scheduled_days = {
        datetime.fromisoformat(str(item["start_at"])).astimezone(SHANGHAI).date() for item in placed
    }
    assert len(placed) == 2
    assert len(scheduled_days) == 2
    assert plan.constraints_snapshot["max_daily_minutes"] == 120
    assert (
        PlanningService.validate_schedule_plan(
            user=user,
            plan_id=plan.pk,
            expected_version=plan.version,
        ).is_valid
        is True
    )

    latest_item = max(placed, key=lambda item: str(item["start_at"]))
    same_day_start = datetime(2026, 7, 27, 11, tzinfo=SHANGHAI).astimezone(UTC).isoformat()
    same_day_end = datetime(2026, 7, 27, 12, 30, tzinfo=SHANGHAI).astimezone(UTC).isoformat()
    for item in plan.items:
        if item.get("task_id") == latest_item["task_id"] and item.get("state") == "placed":
            item["start_at"] = same_day_start
            item["end_at"] = same_day_end
            item["reserved_start_at"] = same_day_start
            item["reserved_end_at"] = same_day_end
    plan.save(update_fields=["items"])
    invalid = PlanningService.validate_schedule_plan(
        user=user,
        plan_id=plan.pk,
        expected_version=plan.version,
    )
    assert invalid.is_valid is False
    assert invalid.reason_codes == ("max_daily_minutes_violation",)


def test_propose_schedule_plan_returns_machine_readable_unplaced_reason() -> None:
    user = get_user_model().objects.create_user(username="plan-unplaced-user")
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Deadline already outside range",
            estimated_minutes=30,
            due_at=datetime(2026, 7, 26, 1, tzinfo=UTC),
        )
    )
    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=datetime(2026, 7, 27, 1, tzinfo=UTC),
        range_end=datetime(2026, 7, 28, 1, tzinfo=UTC),
        strategy="plan_tasks_only",
    )
    task_item = next(item for item in plan.items if item.get("task_id") == str(task.pk))
    assert task_item["state"] == "unplaced"
    assert task_item["reason_codes"] == ["deadline_before_range"]
    assert any(item.get("kind") == "plan_evidence" for item in plan.items)


def test_plan_v2_does_not_schedule_two_tasks_in_same_slot() -> None:
    user = get_user_model().objects.create_user(username="plan-overlap-user")
    tasks = [
        TaskService.create_task(
            CreateTaskCommand(user=user, title=f"Task {index}", estimated_minutes=8)
        )
        for index in range(2)
    ]
    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk for task in tasks],
        range_start=datetime(2026, 7, 27, 1, tzinfo=UTC),
        range_end=datetime(2026, 7, 27, 2, tzinfo=UTC),
        strategy="plan_tasks_only",
    )
    placed = [item for item in plan.items if item.get("state") == "placed"]
    assert len(placed) == 2
    assert placed[0]["end_at"] <= placed[1]["start_at"]


def test_apply_schedule_plan_rejects_conflict_created_after_preview() -> None:
    user = get_user_model().objects.create_user(username="plan-revalidate-user")
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Stale plan target", estimated_minutes=30)
    )
    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=datetime(2026, 7, 27, 1, tzinfo=UTC),
        range_end=datetime(2026, 7, 28, 1, tzinfo=UTC),
        strategy="plan_tasks_only",
    )
    placed = next(item for item in plan.items if item.get("state") == "placed")
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title="New schedule fact",
            start_at=datetime.fromisoformat(str(placed["start_at"])),
            end_at=datetime.fromisoformat(str(placed["end_at"])),
            timezone="Asia/Shanghai",
        )
    )

    with pytest.raises(ValueError, match="schedule_conflict"):
        PlanningService.apply_schedule_plan(
            user=user,
            plan_id=plan.pk,
            expected_version=plan.version,
        )
    task.refresh_from_db()
    plan.refresh_from_db()
    assert task.planned_start_at is None
    assert plan.status == SchedulePlanStatus.INVALIDATED
    assert plan.invalidation_reason == "schedule_conflict"


def test_compare_plans_is_explicit_about_alternatives_not_optimum() -> None:
    user = get_user_model().objects.create_user(username="plan-compare-user")
    tasks = [
        TaskService.create_task(
            CreateTaskCommand(
                user=user,
                title="Short urgent",
                priority="urgent",
                estimated_minutes=30,
            )
        ),
        TaskService.create_task(
            CreateTaskCommand(
                user=user,
                title="Long low",
                priority="low",
                estimated_minutes=90,
            )
        ),
    ]
    result = PlanningService.compare_schedule_plans(
        user=user,
        task_ids=[task.pk for task in tasks],
        range_start=datetime(2026, 7, 27, 1, tzinfo=UTC),
        range_end=datetime(2026, 7, 27, 4, tzinfo=UTC),
        strategy="plan_tasks_only",
    )
    assert result.claim == "deterministic_alternatives_not_global_optimum"
    assert [metric["ordering"] for metric in result.comparison] == [
        "priority_deadline",
        "longest_first",
    ]
    assert all(metric["hard_constraint_violations"] == 0 for metric in result.comparison)


def test_regenerate_plan_only_moves_selected_draft_items() -> None:
    user = get_user_model().objects.create_user(username="plan-regenerate-user")
    tasks = [
        TaskService.create_task(
            CreateTaskCommand(user=user, title=f"Task {index}", estimated_minutes=30)
        )
        for index in range(2)
    ]
    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk for task in tasks],
        range_start=datetime(2026, 7, 27, 1, tzinfo=UTC),
        range_end=datetime(2026, 7, 27, 4, tzinfo=UTC),
        strategy="plan_tasks_only",
    )
    retained_before = next(item for item in plan.items if item.get("task_id") == str(tasks[0].pk))
    regenerated = PlanningService.regenerate_schedule_plan(
        user=user,
        plan_id=plan.pk,
        expected_version=plan.version,
        task_ids=[tasks[1].pk],
        ordering="longest_first",
    )
    retained_after = next(
        item for item in regenerated.items if item.get("task_id") == str(tasks[0].pk)
    )
    evidence = next(
        item["evidence"] for item in regenerated.items if item.get("kind") == "plan_evidence"
    )
    assert retained_after == retained_before
    assert regenerated.version == 2
    assert evidence["regenerated_task_ids"] == [str(tasks[1].pk)]


def test_schedule_plan_persists_constraints_expiry_and_lock_state() -> None:
    user = get_user_model().objects.create_user(username="plan-snapshot-user")
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Snapshot task", estimated_minutes=30)
    )
    anchor = datetime(2026, 7, 27, 0, tzinfo=UTC)

    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=datetime(2026, 7, 27, 1, tzinfo=UTC),
        range_end=datetime(2026, 7, 27, 4, tzinfo=UTC),
        strategy="plan_tasks_only",
        decision_profile_snapshot={"version": 3, "confidence": 0.8},
        now=anchor,
    )

    task_item = next(item for item in plan.items if item.get("task_id") == str(task.pk))
    assert task_item["locked"] is False
    assert plan.constraints_snapshot["snapshot_version"] == "planning-constraints-v1"
    assert plan.constraints_snapshot["timezone"] == "Asia/Shanghai"
    assert plan.decision_profile_snapshot == {"version": 3, "confidence": 0.8}
    assert plan.expires_at > anchor


def test_high_confidence_duration_profile_changes_planned_slot_length() -> None:
    user = get_user_model().objects.create_user(username="plan-duration-profile")
    start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Calibrated task", estimated_minutes=30)
    )

    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=start,
        range_end=start + timedelta(hours=3),
        strategy="plan_tasks_only",
        decision_profile_snapshot={
            "enabled": True,
            "version": 4,
            "confidence": 0.8,
            "sample_count": 10,
            "duration_multiplier": 2.0,
        },
    )

    item = next(item for item in plan.items if item.get("task_id"))
    assert item["base_duration_minutes"] == 30
    assert item["planned_duration_minutes"] == 60
    assert item["duration_source"] == "decision_profile"
    assert item["decision_profile_version"] == 4
    assert item["soft_reason_codes"] == ["high_confidence_duration_calibration"]


def test_low_confidence_duration_profile_keeps_original_estimate() -> None:
    user = get_user_model().objects.create_user(username="plan-low-duration-profile")
    start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Uncalibrated task", estimated_minutes=30)
    )

    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=start,
        range_end=start + timedelta(hours=3),
        strategy="plan_tasks_only",
        decision_profile_snapshot={
            "enabled": True,
            "version": 4,
            "confidence": 0.3,
            "sample_count": 10,
            "duration_multiplier": 2.0,
        },
    )

    item = next(item for item in plan.items if item.get("task_id"))
    assert item["planned_duration_minutes"] == 30
    assert item["duration_source"] == "task_estimate_or_default"
    assert item["soft_reason_codes"] == []


def test_planner_reserves_task_buffers_and_exposes_actual_work_interval() -> None:
    user = get_user_model().objects.create_user(username="plan-buffer")
    start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Buffered task",
            estimated_minutes=30,
            buffer_before_minutes=15,
            buffer_after_minutes=10,
        )
    )

    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=start,
        range_end=start + timedelta(hours=3),
        strategy="plan_tasks_only",
    )

    item = next(item for item in plan.items if item.get("task_id"))
    assert datetime.fromisoformat(item["start_at"]) - datetime.fromisoformat(
        item["reserved_start_at"]
    ) == timedelta(minutes=15)
    assert datetime.fromisoformat(item["reserved_end_at"]) - datetime.fromisoformat(
        item["end_at"]
    ) == timedelta(minutes=10)
    assert item["buffer_before_minutes"] == 15
    assert item["buffer_after_minutes"] == 10


def test_planner_never_moves_task_with_persistent_planning_lock() -> None:
    user = get_user_model().objects.create_user(username="plan-task-lock")
    start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Locked task",
            estimated_minutes=30,
            planning_locked=True,
        )
    )

    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=start,
        range_end=start + timedelta(hours=3),
        strategy="plan_tasks_only",
    )

    item = next(item for item in plan.items if item.get("task_id"))
    assert item["state"] == "unplaced"
    assert item["locked"] is True
    assert item["reason_codes"] == ["task_planning_locked"]


def test_splittable_task_creates_multiple_linked_event_blocks_only_when_needed() -> None:
    user = get_user_model().objects.create_user(username="plan-splittable")
    start = datetime(2026, 8, 24, 1, tzinfo=UTC)
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Middle meeting",
            start_at=start + timedelta(minutes=45),
            end_at=start + timedelta(minutes=75),
            timezone="Asia/Shanghai",
        )
    )
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Split research",
            estimated_minutes=60,
            splittable=True,
            minimum_chunk_minutes=30,
        )
    )

    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=start,
        range_end=start + timedelta(hours=2),
        strategy="create_linked_event_blocks",
    )

    segments = [item for item in plan.items if item.get("task_id")]
    assert len(segments) == 2
    assert [item["segment_index"] for item in segments] == [1, 2]
    assert all(item["segment_count"] == 2 for item in segments)
    assert sum(int(item["planned_duration_minutes"]) for item in segments) == 60

    PlanningService.apply_schedule_plan(
        user=user,
        plan_id=plan.pk,
        expected_version=plan.version,
    )
    assert task.calendar_events.count() == 2


def test_split_accounting_commits_daily_minutes_once_and_counts_tasks_not_segments() -> None:
    user = get_user_model().objects.create_user(username="split-daily-accounting")
    UserPreferenceService.update_for_user(
        user,
        {"timezone": "Asia/Shanghai", "workday_start": time(9), "workday_end": time(17)},
    )
    start = datetime(2026, 8, 24, 9, tzinfo=SHANGHAI)
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Break between focus blocks",
            start_at=start + timedelta(hours=1),
            end_at=start + timedelta(hours=2),
            timezone="Asia/Shanghai",
        )
    )
    split_task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Split task",
            estimated_minutes=60,
            due_at=start + timedelta(hours=3),
            buffer_before_minutes=15,
            buffer_after_minutes=15,
            splittable=True,
            minimum_chunk_minutes=30,
        )
    )
    following_task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Following task", estimated_minutes=60)
    )

    plan = _propose_schedule_plan(
        user=user,
        task_ids=[split_task.pk, following_task.pk],
        range_start=start,
        range_end=start + timedelta(hours=4),
        strategy="create_linked_event_blocks",
        max_daily_minutes=120,
    )

    split_items = [item for item in plan.items if item.get("task_id") == str(split_task.pk)]
    following_item = next(
        item for item in plan.items if item.get("task_id") == str(following_task.pk)
    )
    evidence = next(item["evidence"] for item in plan.items if item.get("kind") == "plan_evidence")

    assert len(split_items) == 2
    assert sum(int(item["planned_duration_minutes"]) for item in split_items) == 60
    assert following_item["state"] == "placed"
    assert evidence["task_count"] == 2
    assert evidence["placed_count"] == 2
    assert evidence["unplaced_count"] == 0
    assert evidence["placed_segment_count"] == 3
    assert evidence["segment_count"] == 3
    metrics = PlanningService._plan_metrics(plan)
    assert metrics["task_count"] == 2
    assert metrics["placed_count"] == 2
    assert metrics["unplaced_count"] == 0
    assert metrics["placed_segment_count"] == 3
    assert metrics["segment_count"] == 3


def test_proposal_excludes_selected_tasks_old_plan_but_keeps_other_plans_busy() -> None:
    user = get_user_model().objects.create_user(username="selected-plan-does-not-block-itself")
    start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    selected = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Selected existing plan",
            estimated_minutes=60,
            planned_start_at=start,
            planned_end_at=start + timedelta(hours=1),
        )
    )
    retained = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Other task keeps its commitment",
            estimated_minutes=60,
            planned_start_at=start + timedelta(hours=1),
            planned_end_at=start + timedelta(hours=2),
        )
    )

    plan = _propose_schedule_plan(
        user=user,
        task_ids=[selected.pk],
        range_start=start,
        range_end=start + timedelta(hours=2),
        strategy="plan_tasks_only",
    )

    item = next(item for item in plan.items if item.get("task_id") == str(selected.pk))
    assert item["state"] == "placed"
    assert datetime.fromisoformat(str(item["reserved_end_at"])) <= retained.planned_start_at


def test_split_plan_item_edit_is_rejected_as_ambiguous() -> None:
    user = get_user_model().objects.create_user(username="split-edit-is-ambiguous")
    start = datetime(2026, 8, 24, 1, tzinfo=UTC)
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Middle meeting",
            start_at=start + timedelta(minutes=45),
            end_at=start + timedelta(minutes=75),
            timezone="Asia/Shanghai",
        )
    )
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Split task to edit",
            estimated_minutes=60,
            splittable=True,
            minimum_chunk_minutes=30,
        )
    )
    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=start,
        range_end=start + timedelta(hours=2),
        strategy="create_linked_event_blocks",
    )

    with pytest.raises(ValueError, match="Split task items cannot be edited by task_id"):
        PlanningService.edit_schedule_plan(
            user=user,
            plan_id=plan.pk,
            expected_version=plan.version,
            edits=[{"task_id": task.pk, "locked": True}],
        )


def test_failed_partial_split_does_not_reserve_trial_slots_or_daily_minutes() -> None:
    user = get_user_model().objects.create_user(username="split-trial-rollback")
    start = datetime(2026, 8, 24, 9, tzinfo=SHANGHAI)
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title="End of available window",
            start_at=start + timedelta(minutes=45),
            end_at=start + timedelta(hours=1),
            timezone="Asia/Shanghai",
        )
    )
    split_task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Cannot finish both chunks",
            estimated_minutes=60,
            priority="urgent",
            splittable=True,
            minimum_chunk_minutes=30,
        )
    )
    normal_task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Use remaining window", estimated_minutes=30)
    )

    plan = _propose_schedule_plan(
        user=user,
        task_ids=[split_task.pk, normal_task.pk],
        range_start=start,
        range_end=start + timedelta(hours=1),
        strategy="create_linked_event_blocks",
        max_daily_minutes=90,
    )
    split_item = next(item for item in plan.items if item.get("task_id") == str(split_task.pk))
    normal_item = next(item for item in plan.items if item.get("task_id") == str(normal_task.pk))

    assert split_item["state"] == "unplaced"
    assert normal_item["state"] == "placed"


def test_regeneration_counts_actual_retained_minutes_and_reserves_buffers() -> None:
    user = get_user_model().objects.create_user(username="regen-buffer-capacity")
    UserPreferenceService.update_for_user(
        user,
        {"timezone": "UTC", "workday_start": time(9), "workday_end": time(17)},
    )
    start = datetime(2026, 8, 24, 9, tzinfo=UTC)
    retained_task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Retained with buffers",
            estimated_minutes=60,
            priority="urgent",
            buffer_before_minutes=15,
            buffer_after_minutes=15,
        )
    )
    selected_task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Regenerate this task",
            estimated_minutes=60,
            priority="low",
        )
    )
    plan = _propose_schedule_plan(
        user=user,
        task_ids=[retained_task.pk, selected_task.pk],
        range_start=start,
        range_end=start + timedelta(hours=8),
        strategy="plan_tasks_only",
        max_daily_minutes=120,
    )
    retained_item = next(
        item for item in plan.items if item.get("task_id") == str(retained_task.pk)
    )

    regenerated = PlanningService.regenerate_schedule_plan(
        user=user,
        plan_id=plan.pk,
        expected_version=plan.version,
        task_ids=[selected_task.pk],
        ordering="priority_deadline",
        now=start,
    )
    selected_item = next(
        item for item in regenerated.items if item.get("task_id") == str(selected_task.pk)
    )

    assert selected_item["state"] == "placed"
    assert datetime.fromisoformat(
        str(selected_item["reserved_start_at"])
    ) >= datetime.fromisoformat(str(retained_item["reserved_end_at"]))
    assert PlanningService.validate_schedule_plan(
        user=user,
        plan_id=regenerated.pk,
        expected_version=regenerated.version,
        now=start,
    ).is_valid


def test_validate_expired_plan_persists_machine_readable_invalidation() -> None:
    user = get_user_model().objects.create_user(username="plan-expired-user")
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Expired plan task", estimated_minutes=30)
    )
    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=datetime(2026, 7, 27, 1, tzinfo=UTC),
        range_end=datetime(2026, 7, 27, 4, tzinfo=UTC),
        strategy="plan_tasks_only",
        now=datetime(2026, 7, 26, 0, tzinfo=UTC),
    )

    result = PlanningService.validate_schedule_plan(
        user=user,
        plan_id=plan.pk,
        expected_version=plan.version,
        now=plan.expires_at + timedelta(seconds=1),
    )

    plan.refresh_from_db()
    assert result.is_valid is False
    assert result.reason_codes == ("plan_expired",)
    assert plan.status == SchedulePlanStatus.INVALIDATED
    assert plan.invalidation_reason == "plan_expired"
    assert plan.invalidated_at is not None


def test_edit_can_lock_and_unlock_a_plan_item_but_regeneration_respects_lock() -> None:
    user = get_user_model().objects.create_user(username="plan-lock-user")
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Locked task", estimated_minutes=30)
    )
    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=datetime(2026, 7, 27, 1, tzinfo=UTC),
        range_end=datetime(2026, 7, 27, 4, tzinfo=UTC),
        strategy="plan_tasks_only",
    )
    locked = PlanningService.edit_schedule_plan(
        user=user,
        plan_id=plan.pk,
        expected_version=plan.version,
        edits=[{"task_id": task.pk, "locked": True}],
    )

    with pytest.raises(ValueError, match="Locked plan items"):
        PlanningService.regenerate_schedule_plan(
            user=user,
            plan_id=locked.pk,
            expected_version=locked.version,
            task_ids=[task.pk],
            ordering="priority_deadline",
        )

    unlocked = PlanningService.edit_schedule_plan(
        user=user,
        plan_id=locked.pk,
        expected_version=locked.version,
        edits=[{"task_id": task.pk, "locked": False}],
    )
    item = next(item for item in unlocked.items if item.get("task_id") == str(task.pk))
    assert item["locked"] is False


def test_edit_can_move_an_item_within_the_same_validated_draft() -> None:
    user = get_user_model().objects.create_user(username="plan-move-user")
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Movable task", estimated_minutes=30)
    )
    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=datetime(2026, 7, 27, 1, tzinfo=UTC),
        range_end=datetime(2026, 7, 27, 4, tzinfo=UTC),
        strategy="plan_tasks_only",
    )

    moved = PlanningService.edit_schedule_plan(
        user=user,
        plan_id=plan.pk,
        expected_version=plan.version,
        edits=[
            {
                "task_id": task.pk,
                "start_at": datetime(2026, 7, 27, 3, tzinfo=UTC),
                "end_at": datetime(2026, 7, 27, 3, 30, tzinfo=UTC),
            }
        ],
    )

    assert moved.pk == plan.pk
    assert moved.version == plan.version + 1
    item = next(item for item in moved.items if item.get("task_id") == str(task.pk))
    assert item["start_at"] == "2026-07-27T03:00:00+00:00"
    assert item["end_at"] == "2026-07-27T03:30:00+00:00"


def test_user_can_abandon_only_a_versioned_draft() -> None:
    user = get_user_model().objects.create_user(username="plan-abandon-user")
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Abandoned task", estimated_minutes=30)
    )
    plan = _propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=datetime(2026, 7, 27, 1, tzinfo=UTC),
        range_end=datetime(2026, 7, 27, 4, tzinfo=UTC),
        strategy="plan_tasks_only",
    )

    abandoned = PlanningService.abandon_schedule_plan(
        user=user,
        plan_id=plan.pk,
        expected_version=plan.version,
    )

    assert abandoned.status == SchedulePlanStatus.ABANDONED
    assert abandoned.abandoned_at is not None
    with pytest.raises(ValueError, match="Only a draft"):
        PlanningService.abandon_schedule_plan(
            user=user,
            plan_id=plan.pk,
            expected_version=abandoned.version,
        )
