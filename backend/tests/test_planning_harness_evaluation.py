from datetime import date
from types import SimpleNamespace

from apps.agents.management.commands.evaluate_planning_harness import Command


def test_agent_candidate_plan_limit_defaults_to_one() -> None:
    assert Command._plan_count_limit_passed(candidate_count=1, maximum=1)
    assert not Command._plan_count_limit_passed(candidate_count=2, maximum=1)
    assert Command._plan_count_limit_passed(candidate_count=3, maximum="unbounded")


def test_clarification_detector_handles_multiline_choices() -> None:
    response = "需要你决定：\n1. 客户甲和客户乙，优先安排哪一个？"

    assert Command._asks_clarification(response)
    assert Command._clarifying_question_count(response) == 1


def test_confirmation_statement_counts_as_one_user_gate() -> None:
    response = "建议移到 10-12 10:30–12:30。需要你确认后我才会执行这次改期。"

    assert Command._asks_clarification(response)
    assert not Command._asks_planning_clarification(response)
    assert Command._clarifying_question_count(response) == 0


def test_explicit_yes_no_action_question_counts_as_clarification() -> None:
    response = "需要我按这个时间提交改期吗？"

    assert Command._asks_clarification(response)
    assert not Command._asks_planning_clarification(response)
    assert Command._clarifying_question_count(response) == 0


def test_direct_priority_question_is_detected() -> None:
    response = "客户甲提案和客户乙风险报告，你要优先安排哪一个？"

    assert Command._asks_clarification(response)
    assert Command._clarifying_question_count(response) == 1


def test_application_confirmation_is_not_a_planning_clarification() -> None:
    response = "草案已准备好。需要我应用这份草案吗？"

    assert not Command._asks_planning_clarification(response)
    assert Command._clarifying_question_count(response) == 0


def test_pending_hitl_interrupt_names_approval_tools() -> None:
    interrupt = SimpleNamespace(
        value={
            "action_requests": [
                {"name": "reschedule_task"},
                {"name": "apply_schedule_plan"},
            ]
        }
    )

    assert Command._pending_approval_tool_names([interrupt]) == [
        "apply_schedule_plan",
        "reschedule_task",
    ]


def test_pending_approval_is_only_reported_for_actual_hitl_payload() -> None:
    assert Command._pending_approval_tool_names([]) == []
    assert Command._pending_approval_tool_names([SimpleNamespace(value={"other": []})]) == []


def test_clarification_question_count_counts_separate_questions() -> None:
    response = "先安排哪一个？\n另一个任务你希望怎么处理？"

    assert Command._clarifying_question_count(response) == 2


def test_schedule_date_parser_ignores_due_date_after_task_title() -> None:
    response = """**10 月 8 日（周四）**
- 09:00–10:00 确认差旅证件（截止 10/9）
"""

    assert Command._schedule_days_in_response(
        response,
        title="确认差旅证件",
        year=2026,
    ) == {date(2026, 10, 8)}


def test_schedule_date_parser_accepts_month_day_hyphen() -> None:
    response = "**10-12**\n- 09:00–10:00 完成差旅审批"

    assert Command._schedule_days_in_response(
        response,
        title="完成差旅审批",
        year=2026,
    ) == {date(2026, 10, 12)}


def test_schedule_date_parser_ignores_deadline_mention_before_task_title() -> None:
    response = """| 10/15 | 09:00–11:00 | 完成团队季度反馈初稿 |
说明：10/16 的完成团队季度反馈初稿截止，但已提前到 10/15 上午。"""

    assert Command._schedule_days_in_response(
        response,
        title="完成团队季度反馈初稿",
        year=2026,
    ) == {date(2026, 10, 15)}


def test_tool_error_summary_distinguishes_recovery_from_terminal_failure() -> None:
    trace = [
        {"name": "get_planning_context", "status": "error"},
        {"name": "get_planning_context", "status": "success"},
        {"name": "propose_schedule_plan", "status": "error"},
    ]

    assert Command._classify_tool_errors(trace) == (
        ["get_planning_context"],
        ["propose_schedule_plan"],
    )


def test_p95_latency_uses_nearest_rank() -> None:
    results = [{"variant": "agent", "duration_seconds": duration} for duration in range(1, 11)]

    assert Command._variant_summaries(results)["agent"]["p95_latency_seconds"] == 10.0


def test_candidate_move_time_must_fit_work_hours_and_returned_slot() -> None:
    scenario = {
        "anchor_at": "2026-10-05T08:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "workday_start": "09:00",
        "workday_end": "17:00",
    }
    response = "建议的新时间：10/12 16:00–18:00"

    violations = Command._candidate_time_violations(
        response,
        scenario=scenario,
        tool_trace=[],
    )

    assert "suggested_time_outside_work_hours" in violations
    assert "suggested_time_missing_free_slot_evidence" in violations


def test_clarification_target_accepts_scenario_alias() -> None:
    scenario = {
        "expectations": {
            "ask_user_about_task_keys": ["client_a_proposal"],
            "ask_user_task_aliases": {"client_a_proposal": ["客户甲提案"]},
        },
        "tasks": [
            {
                "key": "client_a_proposal",
                "title": "完成客户甲合作提案",
            }
        ],
    }

    assert Command._clarification_targets_met(scenario, "客户甲提案和客户乙报告，优先安排哪一个？")


def test_candidate_time_matching_returned_free_slot_is_valid() -> None:
    scenario = {
        "anchor_at": "2026-10-05T08:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "workday_start": "09:00",
        "workday_end": "17:00",
    }
    tool_trace: list[dict[str, object]] = [
        {
            "name": "get_planning_context",
            "status": "success",
            "arguments": {"mode": "free_slots"},
            "observation": (
                '{"free_slots":[{"start_at":"2026-10-12T02:30:00+00:00",'
                '"end_at":"2026-10-12T04:30:00+00:00"}]}'
            ),
        }
    ]

    assert (
        Command._candidate_time_violations(
            "请确认是否把任务改到 10-12 10:30–12:30？",
            scenario=scenario,
            tool_trace=tool_trace,
        )
        == []
    )


def test_reschedule_tool_candidate_requires_timezone_slot_and_deadline_evidence() -> None:
    scenario = {
        "anchor_at": "2026-10-05T08:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "workday_start": "09:00",
        "workday_end": "17:00",
        "tasks": [{"key": "data_analysis", "due_at": "2026-10-15T17:00:00+08:00"}],
    }
    tool_trace: list[dict[str, object]] = [
        {
            "name": "get_planning_context",
            "status": "success",
            "arguments": {"mode": "free_slots"},
            "observation": (
                '{"free_slots":[{"start_at":"2026-10-12T03:00:00+00:00",'
                '"end_at":"2026-10-12T05:00:00+00:00"}]}'
            ),
        },
        {
            "name": "reschedule_task",
            "status": "unknown",
            "arguments": {
                "task_id": "data_analysis",
                "planned_start_at": "2026-10-12T11:00:00+08:00",
                "planned_end_at": "2026-10-12T13:00:00+08:00",
            },
        },
    ]

    assert (
        Command._candidate_time_violations(
            "",
            scenario=scenario,
            tool_trace=tool_trace,
        )
        == []
    )

    arguments = tool_trace[1]["arguments"]
    assert isinstance(arguments, dict)
    arguments["planned_end_at"] = "2026-10-12T18:00:00+08:00"
    violations = Command._candidate_time_violations(
        "",
        scenario=scenario,
        tool_trace=tool_trace,
    )
    assert "reschedule_tool_time_outside_work_hours" in violations
    assert "reschedule_tool_time_missing_free_slot_evidence" in violations


def test_replan_quality_requires_the_smallest_supported_schedule_shift() -> None:
    scenario = {
        "anchor_at": "2026-10-05T08:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "expectations": {
            "expected_moved_task_keys": ["data_analysis"],
            "max_moved_tasks": 1,
            "max_total_shift_minutes": 240,
        },
        "tasks": [
            {
                "key": "data_analysis",
                "flags": {
                    "planned_start_at": "2026-10-12T13:00:00+08:00",
                    "planned_end_at": "2026-10-12T15:00:00+08:00",
                },
            }
        ],
    }
    trace = [
        {
            "name": "get_planning_context",
            "status": "success",
            "arguments": {"mode": "free_slots"},
            "observation": (
                '{"free_slots":[{"start_at":"2026-10-12T02:30:00+00:00",'
                '"end_at":"2026-10-12T04:30:00+00:00"},'
                '{"start_at":"2026-10-12T03:00:00+00:00",'
                '"end_at":"2026-10-12T05:00:00+00:00"}]}'
            ),
        }
    ]

    earlier = Command._replan_candidate_metrics(
        response="最小移动方案：移到 10 月 12 日 10:30–12:30",
        scenario=scenario,
        tool_trace=trace,
    )
    assert earlier["total_shift_minutes"] == 300
    assert earlier["checks"]["max_total_shift_minutes"] is False
    assert earlier["checks"]["minimum_available_shift"] is False

    nearest = Command._replan_candidate_metrics(
        response="最小移动方案：移到 10 月 12 日 11:00–13:00",
        scenario=scenario,
        tool_trace=trace,
    )
    assert nearest["passed"] is True
    assert nearest["total_shift_minutes"] == 240
