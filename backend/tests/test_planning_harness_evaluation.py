import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from django.contrib.auth.models import User
from django.core.management.base import CommandError

from apps.agents.management.commands.evaluate_planning_harness import Command
from apps.planning.models import SchedulePlan
from apps.tasks.models import Task


def test_agent_candidate_plan_limit_defaults_to_one() -> None:
    assert Command._plan_count_limit_passed(candidate_count=1, maximum=1)
    assert not Command._plan_count_limit_passed(candidate_count=2, maximum=1)
    assert Command._plan_count_limit_passed(candidate_count=3, maximum="unbounded")


def test_explicit_comparison_allows_two_candidates_and_requires_both_orderings() -> None:
    def evidence(ordering: str) -> SchedulePlan:
        return cast(
            SchedulePlan,
            SimpleNamespace(items=[{"kind": "plan_evidence", "ordering": ordering}]),
        )

    trace = [{"name": "compare_schedule_plans", "status": "success"}]

    assert Command._max_candidate_plans({"explicit_plan_comparison": True}) == 2
    assert Command._max_candidate_plans({}) == 1
    assert Command._explicit_comparison_met(
        [evidence("priority_deadline"), evidence("longest_first")], trace
    )
    assert not Command._explicit_comparison_met([evidence("priority_deadline")], trace)
    assert not Command._explicit_comparison_met(
        [evidence("priority_deadline"), evidence("priority_deadline")], trace
    )


def test_duplicate_read_metric_only_counts_same_successful_tool_and_arguments() -> None:
    trace = [
        {"name": "list_tasks", "arguments": {"statuses": ["pending"]}, "status": "success"},
        {"name": "list_tasks", "arguments": {"statuses": ["pending"]}, "status": "success"},
        {"name": "list_tasks", "arguments": {"statuses": ["completed"]}, "status": "success"},
        {"name": "list_tasks", "arguments": {"statuses": ["pending"]}, "status": "error"},
    ]

    assert Command._duplicate_read_count(trace) == 1


@pytest.mark.django_db(transaction=True)
def test_planner_evaluator_does_not_pass_expectations_into_agent_runtime() -> None:
    user = User.objects.create_user(username="expectation-isolation")
    captured: dict[str, Any] = {}

    class CapturingAgent:
        @staticmethod
        def invoke(inputs: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
            captured["inputs"] = inputs
            captured.update(kwargs)
            return {
                "messages": [
                    *inputs["messages"],
                    SimpleNamespace(content="完成计划", tool_calls=[]),
                ]
            }

    scenario = {
        "id": "expectation-isolation",
        "prompt": "下周帮我安排这些任务",
        "anchor_at": "2026-10-05T00:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "expectations": {
            "phase_windows": [{"name": "secret-evaluator-target"}],
            "preferred_unplaced_task_keys": ["only-for-score"],
        },
    }

    Command()._invoke_agent(
        agent=CapturingAgent(),
        user=user,
        scenario=scenario,
        request_id="expectation-isolation-request",
        task_map={},
    )

    runtime = captured["context"]
    assert runtime.input_message == scenario["prompt"]
    assert "expectations" not in captured["inputs"]
    assert "secret-evaluator-target" not in str(captured["inputs"])
    assert "only-for-score" not in str(captured["inputs"])


def test_request_contract_requires_prompt_evidence_for_user_requested_ranges(
    tmp_path: Path,
) -> None:
    scenario = {
        "id": "range-evidence",
        "prompt": "把任务安排在下周",
        "request_contract": {
            "intent": "schedule_plan",
            "write_policy": "allow_schedule_draft",
            "intent_quote": "任务安排",
            "user_requested_range": {
                "source_quote": "10 月 8 日至 10 月 10 日",
                "start_at": "2026-10-08T00:00:00+08:00",
                "end_at": "2026-10-11T00:00:00+08:00",
            },
        },
    }
    fixture = tmp_path / "bad-range.json"
    fixture.write_text(json.dumps({"scenarios": [scenario]}), encoding="utf-8")

    with pytest.raises(CommandError, match="quote from its prompt"):
        Command._load_scenarios(fixture)


def test_holdout_scenarios_require_an_explicit_request_contract(tmp_path: Path) -> None:
    fixture = tmp_path / "untyped-holdout.json"
    fixture.write_text(
        json.dumps({"scenarios": [{"id": "untyped", "split": "holdout"}]}),
        encoding="utf-8",
    )

    with pytest.raises(CommandError, match="needs a request_contract"):
        Command._load_scenarios(fixture)


def test_diagnostic_fixture_distinguishes_schedule_windows_from_deadlines() -> None:
    fixture = Command._default_dataset_path().parent / "agent_harness_v2_diagnostic_regression.json"
    scenarios = {item["id"]: item for item in Command._load_scenarios(fixture)}
    accessibility = scenarios["sealed_final_22_accessibility_audit"]
    survey = scenarios["sealed_final_29_civic_survey"]

    assert accessibility["request_contract"]["user_requested_range"] == {
        "source_quote": "11月30日至12月9日",
        "start_at": "2026-11-30T00:00:00-07:00",
        "end_at": "2026-12-10T00:00:00-07:00",
    }
    assert survey["request_contract"]["user_requested_range"] == {
        "source_quote": "12月7日至12月27日",
        "start_at": "2026-12-07T00:00:00+01:00",
        "end_at": "2026-12-28T00:00:00+01:00",
    }
    assert all(
        datetime.fromisoformat(task["due_at"]).date() <= date(2026, 12, 20)
        for task in survey["tasks"]
    )


def test_evaluator_uses_only_user_requested_range_not_fixture_search_window() -> None:
    scenario = {
        "id": "search-window-is-not-a-user-constraint",
        "prompt": "安排这项任务",
        "anchor_at": "2026-10-05T08:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "range_start": "2026-10-08T00:00:00+08:00",
        "range_end": "2026-10-20T00:00:00+08:00",
        "workday_start": "09:00",
        "workday_end": "17:00",
        "tasks": [{"key": "task", "title": "Report", "flags": {}}],
        "events": [],
        "expectations": {},
    }
    task_map: dict[str, Any] = {"task": cast(Task, SimpleNamespace(pk="task-id"))}
    plan = cast(
        SchedulePlan,
        SimpleNamespace(
            pk="plan-id",
            strategy="plan_tasks_only",
            status="draft",
            items=[
                {
                    "task_id": "task-id",
                    "state": "placed",
                    "start_at": "2026-10-06T10:00:00+08:00",
                    "end_at": "2026-10-06T11:00:00+08:00",
                    "planned_duration_minutes": 60,
                }
            ],
        ),
    )

    metrics = Command._plan_metrics(
        scenario=scenario,
        plan=plan,
        task_map=task_map,
        final_response="",
    )

    assert "outside_range:task" not in metrics["hard_violations"]
    assert "outside_user_requested_range:task" not in metrics["hard_violations"]

    scenario["request_contract"] = {
        "intent": "schedule_plan",
        "write_policy": "allow_schedule_draft",
        "intent_quote": "安排这项任务",
        "user_requested_range": {
            "source_quote": "10 月 8 日至 10 月 10 日",
            "start_at": "2026-10-08T00:00:00+08:00",
            "end_at": "2026-10-11T00:00:00+08:00",
        },
    }
    scenario["prompt"] = "请在 10 月 8 日至 10 月 10 日安排这项任务"

    metrics = Command._plan_metrics(
        scenario=scenario,
        plan=plan,
        task_map=task_map,
        final_response="",
    )

    assert "outside_user_requested_range:task" in metrics["hard_violations"]


def test_request_intent_defines_valid_no_plan_success_and_baseline_scope() -> None:
    workflow = Command._workflow_succeeded

    assert workflow(
        request_intent="read_only_answer",
        variant="agent",
        candidate_count=0,
        asked_clarification=False,
        approval_pending=False,
        clarification_expected=False,
        approval_expected=False,
    )
    assert not workflow(
        request_intent="read_only_answer",
        variant="agent",
        candidate_count=1,
        asked_clarification=False,
        approval_pending=False,
        clarification_expected=False,
        approval_expected=False,
    )
    assert workflow(
        request_intent="clarification",
        variant="agent",
        candidate_count=0,
        asked_clarification=True,
        approval_pending=False,
        clarification_expected=True,
        approval_expected=False,
    )
    assert not workflow(
        request_intent="clarification",
        variant="baseline",
        candidate_count=1,
        asked_clarification=False,
        approval_pending=False,
        clarification_expected=True,
        approval_expected=False,
    )
    assert not workflow(
        request_intent="schedule_plan",
        variant="agent",
        candidate_count=0,
        asked_clarification=False,
        approval_pending=False,
        clarification_expected=False,
        approval_expected=False,
    )


def test_clarification_detector_handles_multiline_choices() -> None:
    response = "需要你决定：\n1. 客户甲和客户乙，优先安排哪一个？"

    assert Command._asks_clarification(response)
    assert Command._clarifying_question_count(response) == 1


def test_pre_draft_dependency_question_is_detected_in_english() -> None:
    response = "Before I draft, I need your call on which date range to use."

    assert Command._asks_planning_clarification(response)
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


def test_priority_and_deadline_table_heading_is_not_a_clarification() -> None:
    response = "**已排入（按优先级 + 截止日期）**\n| 任务 | 优先级 | 截止 | 安排 |"

    assert not Command._asks_planning_clarification(response)
    assert Command._clarifying_question_count(response) == 0


def test_application_confirmation_is_not_a_planning_clarification() -> None:
    response = "草案已准备好。需要我应用这份草案吗？"

    assert not Command._asks_planning_clarification(response)
    assert Command._clarifying_question_count(response) == 0


def test_optional_post_plan_adjustment_offer_is_not_a_planning_clarification() -> None:
    response = (
        "草案已生成，全部任务均已排入。"
        "如需拆分到两天，我可以调整。若你希望把复盘合并到该时段，也可以改。"
        "需要我应用这份草案吗？"
    )

    assert not Command._asks_planning_clarification(response)
    assert Command._clarifying_question_count(response) == 0


def test_capacity_tradeoff_decision_statement_is_not_a_clarification() -> None:
    response = "如果确实需要完成剩下任务，需放宽截止；这需要你来决定。"

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


def test_schedule_date_parser_infers_year_across_new_year_boundary() -> None:
    response = "**1/1（周五）**\n- 10:00–11:00 核对云端和硬盘备份"

    assert Command._schedule_days_in_response(
        response,
        title="核对云端和硬盘备份",
        year=2026,
        reference_days={date(2027, 1, 1)},
    ) == {date(2027, 1, 1)}


def test_schedule_date_parser_ignores_deadline_mention_before_task_title() -> None:
    response = """| 10/15 | 09:00–11:00 | 完成团队季度反馈初稿 |
说明：10/16 的完成团队季度反馈初稿截止，但已提前到 10/15 上午。"""

    assert Command._schedule_days_in_response(
        response,
        title="完成团队季度反馈初稿",
        year=2026,
    ) == {date(2026, 10, 15)}


def test_schedule_date_parser_ignores_due_date_in_later_explanatory_prose() -> None:
    response = """**10 月 14 日（周三）**
- 11:00–11:45 整理评审会行动项
说明：任务整理评审会行动项的截止日是 10 月 15 日。"""

    assert Command._schedule_days_in_response(
        response,
        title="整理评审会行动项",
        year=2026,
    ) == {date(2026, 10, 14)}


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


def test_candidate_time_matching_created_plan_item_is_valid_evidence() -> None:
    scenario = {
        "anchor_at": "2026-10-05T08:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "workday_start": "09:00",
        "workday_end": "17:00",
    }

    assert (
        Command._candidate_time_violations(
            "建议安排到 10-12 10:30–12:30。",
            scenario=scenario,
            tool_trace=[],
            plan_intervals=[("2026-10-12T02:30:00+00:00", "2026-10-12T04:30:00+00:00")],
        )
        == []
    )


def test_candidate_time_checker_ignores_mentioned_existing_event_range() -> None:
    scenario = {
        "anchor_at": "2026-11-18T10:00:00-07:00",
        "timezone": "America/Phoenix",
        "workday_start": "08:00",
        "workday_end": "17:00",
        "events": [
            {
                "title": "指挥排练",
                "start_at": "2026-11-23T18:00:00-07:00",
                "end_at": "2026-11-23T19:30:00-07:00",
            }
        ],
    }

    assert (
        Command._candidate_time_violations(
            "- 周一指挥排练：11-23 的 18:00–19:30 已避开（建议时段在上午）",
            scenario=scenario,
            tool_trace=[],
        )
        == []
    )
    parent_scenario = {
        "anchor_at": "2026-10-05T08:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "workday_start": "09:00",
        "workday_end": "17:00",
        "events": [
            {
                "title": "季度部门业务评审",
                "start_at": "2026-10-15T09:30:00+08:00",
                "end_at": "2026-10-15T11:00:00+08:00",
            }
        ],
    }
    assert (
        Command._candidate_time_violations(
            "保留的既有日程均未被占用：10-15 09:30–11:00 "
            "季度部门业务评审（报销凭证因此挪到当天下午）",
            scenario=parent_scenario,
            tool_trace=[],
        )
        == []
    )
    assert "suggested_time_missing_free_slot_evidence" in Command._candidate_time_violations(
        "建议把报销任务挪到 10-15 09:30–11:00，与季度部门业务评审同时",
        scenario=parent_scenario,
        tool_trace=[],
    )
    assert {
        "suggested_time_outside_work_hours",
        "suggested_time_missing_free_slot_evidence",
    } <= set(
        Command._candidate_time_violations(
            "建议改到 11-23 18:00–19:30",
            scenario=scenario,
            tool_trace=[],
        )
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


def test_calendar_uncertainty_statement_is_not_a_planning_question() -> None:
    response = (
        "草案已生成。日历没有晚餐事件，因此无法确认晚餐具体在什么时间；"
        "草案没有与已返回事件重叠。需要我应用这份草案吗？"
    )

    assert not Command._asks_planning_clarification(response)
    assert Command._clarifying_question_count(response) == 0


def test_long_priority_question_is_counted_as_planning_clarification() -> None:
    response = (
        "客户甲提案和客户乙风险报告，你希望优先安排哪一个占用 10 月 16 日 14:00–17:00 "
        "这个唯一的三小时块？"
    )

    assert Command._asks_planning_clarification(response)
    assert Command._clarifying_question_count(response) == 1


def test_alternative_slot_allocation_question_counts_as_planning_clarification() -> None:
    response = (
        "需要你决定的一点：在截止日前，如果确实只有一个可用的三小时块，"
        "你希望这个块先给客户甲提案还是客户乙风险报告？"
    )

    assert Command._asks_planning_clarification(response)
    assert Command._clarifying_question_count(response) == 1


def test_portfolio_diagnostic_is_a_schedule_request() -> None:
    fixture = Command._default_dataset_path().parent / "agent_harness_v3_diagnostic_regression.json"
    scenarios = {item["id"]: item for item in Command._load_scenarios(fixture)}
    scenario = scenarios["h03_26"]

    assert scenario["request_contract"]["intent"] == "schedule_plan"
    assert scenario["request_contract"]["write_policy"] == "allow_schedule_draft"
    assert scenario["request_contract"]["intent_quote"] in scenario["prompt"]


def test_v3_explicit_schedule_requests_are_not_typed_as_read_only() -> None:
    fixture = Command._default_dataset_path().parent / "agent_harness_v3_diagnostic_regression.json"
    scenarios = {item["id"]: item for item in Command._load_scenarios(fixture)}
    for scenario_id in ("h03_03", "h03_05", "h03_08", "h03_13", "h03_22"):
        contract = scenarios[scenario_id]["request_contract"]
        assert contract["intent"] == "schedule_plan"
        assert contract["write_policy"] == "allow_schedule_draft"
        assert contract["intent_quote"] in scenarios[scenario_id]["prompt"]
