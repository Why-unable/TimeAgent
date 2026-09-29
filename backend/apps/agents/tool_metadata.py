"""Declarative tool behavior metadata shared by runtime policy and tooling."""

from __future__ import annotations

from typing import Literal

ToolEffect = Literal["read", "derive", "draft", "business_write", "handoff"]


# A tool may belong to more than one pack when it is a common dependency.
PACK_TOOL_NAMES: dict[str, frozenset[str]] = {
    "overview": frozenset(
        {
            "list_events",
            "list_tasks",
            "list_reminders",
        }
    ),
    "calendar": frozenset(
        {
            "list_events",
            "get_event",
            "mutate_events",
            "create_recurring_event",
        }
    ),
    "tasks": frozenset(
        {
            "list_tasks",
            "get_task",
            "get_task_execution_summary",
            "create_task",
            "create_task_batch",
            "update_task",
            "change_task_state",
            "change_task_batch_state",
            "complete_task",
            "reschedule_task",
            "cancel_task",
        }
    ),
    "reminders": frozenset(
        {
            "list_reminders",
            "get_reminder",
            "create_reminder",
            "update_reminder",
            "set_reminder_target",
            "cancel_reminder",
        }
    ),
    "availability": frozenset({"get_planning_context"}),
    "clock": frozenset({"get_current_datetime"}),
    "planning_preview": frozenset(
        {
            "get_planning_context",
            "propose_schedule_plan",
        }
    ),
    "plan_comparison": frozenset({"compare_schedule_plans"}),
    "duration_guidance": frozenset({"recommend_task_duration"}),
    "plan_review": frozenset(
        {
            "get_planning_context",
            "validate_schedule_plan",
            "edit_schedule_plan",
            "abandon_schedule_plan",
            "apply_schedule_plan",
        }
    ),
    "plan_adaptation": frozenset(
        {
            "detect_schedule_disruptions",
            "get_planning_context",
            "get_task",
            "reschedule_task",
        }
    ),
    "automation_replan": frozenset(
        {
            "list_automation_policies",
            "apply_local_replan",
            "detect_schedule_disruptions",
            "get_planning_context",
        }
    ),
    "time_insights": frozenset(
        {
            "list_temporal_insights",
            "get_temporal_insight",
            "act_on_temporal_insight",
            "search_time_memories",
            "remember_time_preference",
            "update_time_preference",
            "forget_time_preference",
            "record_task_duration_feedback",
            "recommend_task_duration",
            "get_capacity_forecast",
            "get_task_execution_summary",
        }
    ),
    "integrations": frozenset({"list_calendar_sync_status"}),
    "briefing_handoff": frozenset({"transfer_to_briefing"}),
}

DRAFT_TOOL_NAMES = frozenset(
    {
        "propose_schedule_plan",
        "compare_schedule_plans",
        "edit_schedule_plan",
        "abandon_schedule_plan",
    }
)
DERIVE_TOOL_NAMES = frozenset({"list_temporal_insights", "validate_schedule_plan"})
HANDOFF_TOOL_NAMES = frozenset({"transfer_to_briefing"})


# This is the source of truth for both static HITL configuration and tool
# metadata. Conditional approval checks remain in trusted middleware code.
HITL_POLICY_METADATA: dict[str, tuple[tuple[str, ...], str]] = {
    "mutate_events": (
        ("approve", "edit", "reject"),
        "Applies one atomic set of calendar changes and needs one confirmation.",
    ),
    "create_task_batch": (
        ("approve", "edit", "reject"),
        "Creates several tasks in one atomic batch and needs one confirmation.",
    ),
    "create_recurring_event": (
        ("approve", "edit", "reject"),
        "Creates a finite series of calendar commitments and needs one confirmation.",
    ),
    "apply_schedule_plan": (
        ("approve", "reject"),
        "Applies a saved schedule plan to tasks or calendar events atomically.",
    ),
    "apply_local_replan": (
        ("approve", "reject"),
        "Moves an explicitly selected set of flexible tasks as one reversible batch.",
    ),
    "change_task_batch_state": (
        ("approve", "reject"),
        "Changes several task states atomically and needs one confirmation.",
    ),
    "reschedule_task": (
        ("approve", "reject"),
        "Submit an explicitly requested move for approval; "
        "the task stays unchanged until approved.",
    ),
    "update_reminder": (
        ("approve", "edit", "reject"),
        "Changing a reminder's timing or delivery requires confirmation.",
    ),
    "set_reminder_target": (
        ("approve", "edit", "reject"),
        "Changing what a reminder is bound to requires confirmation.",
    ),
    "cancel_reminder": (
        ("approve", "reject"),
        "取消提醒后将不会再按计划通知，需要确认后执行。",
    ),
    "cancel_task": (
        ("approve", "reject"),
        "取消任务会终止其后续执行计划，需要确认后执行。",
    ),
    "remember_time_preference": (
        ("approve", "reject"),
        "保存长期时间偏好会影响未来的 Agent 上下文，需要确认后生效。",
    ),
    "update_time_preference": (
        ("approve", "reject"),
        "修改长期时间偏好会影响未来的 Agent 决策，需要确认后生效。",
    ),
    "forget_time_preference": (
        ("approve", "reject"),
        "忘记长期时间偏好会移除后续 Agent 可用的上下文，需要确认后生效。",
    ),
}
