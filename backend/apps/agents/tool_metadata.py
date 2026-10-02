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
            "request_plan_interaction",
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
        "request_plan_interaction",
    }
)
DERIVE_TOOL_NAMES = frozenset({"list_temporal_insights", "validate_schedule_plan"})
HANDOFF_TOOL_NAMES = frozenset({"transfer_to_briefing"})

# Search-only metadata enriches the registered tool description for discovery. It
# never changes tool behavior, access checks, or service validation.
TOOL_SEARCH_KEYWORDS: dict[str, tuple[str, ...]] = {
    "get_current_datetime": ("现在几点", "当前时间", "今天几号", "what time is it", "current date"),
    "list_events": ("看日程", "查询会议", "calendar agenda", "list events"),
    "get_event": ("查看单个日程", "会议详情", "event details"),
    "mutate_events": ("创建修改取消日程", "新建会议", "edit calendar event"),
    "create_recurring_event": ("重复日程", "周期会议", "recurring calendar event"),
    "list_tasks": ("待办清单", "任务列表", "list todos", "task lookup"),
    "get_task": ("任务详情", "查看任务", "task details"),
    "get_task_execution_summary": ("实际用时", "任务执行记录", "task duration history"),
    "create_task": ("新增待办", "创建任务", "add a task"),
    "create_task_batch": ("批量新增任务", "创建多项待办", "create tasks in bulk"),
    "update_task": ("修改任务信息", "编辑任务属性", "edit task fields"),
    "change_task_state": ("标记进行中", "任务状态", "change task progress"),
    "change_task_batch_state": ("批量完成任务", "批量取消任务", "bulk task status"),
    "complete_task": ("完成任务", "记录任务完成", "mark task complete"),
    "reschedule_task": ("单个任务改时间", "移动一项任务", "move one task"),
    "cancel_task": ("取消待办", "删除任务", "cancel a task"),
    "list_reminders": ("提醒列表", "查看提醒", "list reminders"),
    "get_reminder": ("提醒详情", "查看单个提醒", "reminder details"),
    "create_reminder": ("设置提醒", "提醒我", "create a reminder"),
    "update_reminder": ("修改提醒", "调整提醒时间", "edit reminder"),
    "set_reminder_target": ("更改提醒对象", "关联任务提醒", "change reminder target"),
    "cancel_reminder": ("关闭提醒", "取消通知", "cancel reminder"),
    "get_planning_context": (
        "查可用时间",
        "空档",
        "任务日程工作时段规划上下文",
        "free slots",
        "schedule context",
    ),
    "propose_schedule_plan": (
        "安排任务",
        "生成排程草案",
        "规划明天",
        "schedule tasks",
        "draft a plan",
    ),
    "compare_schedule_plans": ("比较排程方案", "对比两个计划", "compare schedule options"),
    "detect_schedule_disruptions": ("找排程冲突", "被会议打断", "detect schedule conflicts"),
    "list_automation_policies": ("自动重排规则", "重排策略", "automation replanning policy"),
    "validate_schedule_plan": ("校验计划", "验证草案", "validate schedule draft"),
    "edit_schedule_plan": (
        "修改计划时间",
        "把论文改到",
        "编辑排程草案",
        "move planned task",
        "edit schedule plan",
    ),
    "abandon_schedule_plan": ("放弃草案", "不要这个计划", "discard schedule draft"),
    "apply_schedule_plan": ("执行计划", "按计划安排", "apply schedule plan"),
    "apply_local_replan": ("按策略重新排程", "自动调整计划", "apply local replan"),
    "recommend_task_duration": ("任务需要多久", "估算任务时长", "estimate duration"),
    "get_capacity_forecast": ("可用容量", "还能安排多久", "capacity forecast"),
    "record_task_duration_feedback": ("实际做了多久", "记录实际耗时", "duration feedback"),
    "list_calendar_sync_status": ("日历同步状态", "日历连接问题", "calendar sync status"),
    "list_temporal_insights": ("时间使用洞察", "工作节奏分析", "time usage insights"),
    "get_temporal_insight": ("洞察详情", "某条时间分析", "insight details"),
    "act_on_temporal_insight": ("处理时间洞察", "采纳分析建议", "act on insight"),
    "search_time_memories": ("以前的时间偏好", "过去的习惯", "search time preferences"),
    "remember_time_preference": ("记住我的安排习惯", "保存时间偏好", "remember a preference"),
    "update_time_preference": ("修改长期时间偏好", "更新安排习惯", "update time preference"),
    "forget_time_preference": ("忘记时间偏好", "删除记忆偏好", "forget a time preference"),
    "transfer_to_briefing": ("生成简报", "晨报", "daily briefing"),
    "request_plan_interaction": ("计划时间线交互", "任务优先顺序界面", "interactive plan timeline"),
}

# Lifecycle is inferred from successful tool messages and remains a discovery
# hint only; execution still checks run mode, actor, HITL, and domain services.
TOOL_LIFECYCLE_PHASES: dict[str, frozenset[str]] = {
    "propose_schedule_plan": frozenset({"no_plan"}),
    "compare_schedule_plans": frozenset({"no_plan"}),
    "edit_schedule_plan": frozenset({"any"}),
    "validate_schedule_plan": frozenset({"any"}),
    "apply_schedule_plan": frozenset({"any"}),
    "abandon_schedule_plan": frozenset({"any"}),
    "request_plan_interaction": frozenset({"any"}),
}

# Kept empty until usage and A/B evidence justifies permanently eager schemas.
DEFAULT_ALWAYS_EAGER_TOOL_NAMES: frozenset[str] = frozenset()


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
