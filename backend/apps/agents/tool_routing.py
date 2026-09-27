"""Conservative request-to-tool-pack selection for the Time Steward harness."""

from __future__ import annotations

import re

from apps.agents.tool_metadata import PACK_TOOL_NAMES

_PACK_INTENTS: dict[str, tuple[str, ...]] = {
    "overview": (
        r"(?:今天|今日|明天|后天|这周|本周|下周|本月|这月|未来(?:一|两|三|几)?周).{0,12}(?:安排|日程|计划|忙|空|有什么|有哪些)",
        r"(?:安排|日程|计划|忙不忙).{0,10}(?:今天|明天|这周|本周|下周|本月)",
        r"\b(?:today|tomorrow|this week|next week).{0,24}\b(?:schedule|agenda|plans?)\b",
    ),
    "calendar": (r"日程|日历|会议|会面|日历事件|\b(?:calendar|event|meeting)s?\b",),
    "tasks": (r"任务|待办|\btasks?\b|\btodos?\b",),
    "reminders": (r"提醒|\breminders?\b",),
    "availability": (
        r"空闲|空档|空余时间|可安排时段|"
        r"(?:找|推荐).{0,12}(?:时间|时段|晚上|早上|上午|下午|午休|夜间)|"
        r"\b(?:free slots?|availability)\b",
    ),
    "planning_preview": (
        r"排期|排程|排到|排入|排下|规划|帮我安排|安排(?:一下|任务|这些|课程|工作)|"
        r"安排.{0,8}(?:任务|待办|事情|事项|要做)|"
        r"\bschedule\s+(?:(?:two|three|four|several|multiple|some|\d+)\s+)?tasks?\b|\bplanning\b",
    ),
    "plan_adaptation": (
        r"冲突|被打断|重排|重新安排|改期|改时间|移动已排|调整已排|"
        r"\b(?:disruptions?|blocked time|reschedule)\b",
    ),
    "automation_replan": (
        r"自动化策略|自动重排|自动调整策略|重排策略|"
        r"\b(?:automation policy|automated replanning)\b",
    ),
    "time_insights": (
        r"洞察|时间偏好|时间习惯|作息|估时|估算时长|实际做了多久|工作量|容量|记忆|习惯规律|"
        r"\b(?:insights?|duration estimate|capacity forecast)\b",
    ),
    "integrations": (
        r"同步状态|日历连接|日历同步|外部日历|连接状态|\b(?:calendar sync|integration status)\b",
    ),
    "briefing_handoff": (r"简报|晨报|日报|\bbriefings?\b",),
}
_READ_ONLY_INTENT = re.compile(
    r"只(?:看|查|读|分析|给建议|要建议)|只给.{0,4}建议|只是查询|"
    r"(?:先)?不要(?:创建|新增|修改|改动|移动|调整|保存|执行)|"
    r"不需要(?:创建|修改|调整)|保持(?:原样|不变)|\bread.only\b|\bno changes?\b",
    re.IGNORECASE,
)
_QUERY_ONLY_INTENT = re.compile(
    r"看看|看一下|查看|查询|列出|告诉我|是什么|有哪些|有什么|有啥|什么是|为什么|为何|哪里|"
    r"是否|有没有|吗[？?]|\?|\b(?:show|list|check|explain|what is|how many)\b",
    re.IGNORECASE,
)
_EXPLICIT_WRITE_INTENT = re.compile(
    r"创建|新增|添加|设置|保存|修改|改动|移动|调整|安排|排程|排期|重排|取消|删除|"
    r"应用|执行|记住|提醒我|\b(?:create|add|set|save|change|move|reschedule|cancel|delete|apply)\b",
    re.IGNORECASE,
)
_SENSITIVE_OR_CROSS_USER_REQUEST = re.compile(
    r"系统提示词|system prompt|其他用户|他人的|别人的|\bother users?\b|someone else(?:'s)?|"
    r"原始聊天|原始记忆|内部字段|raw conversations?|"
    r"(?:输出|泄露|导出|窃取|reveal|expose|print|show).{0,30}"
    r"(?:api\s*key|\btoken\b|环境变量|credentials?)",
    re.IGNORECASE,
)
_VAGUE_PLANNING_REQUEST = re.compile(
    r"找(?:个|一个)?时间安排一下(?:重要的事|事情|某件事)|最近找时间安排一下|"
    r"安排一下(?:重要的事|事情|某件事)",
    re.IGNORECASE,
)
_MULTI_TASK_SCHEDULE_REQUEST = re.compile(
    r"(?:两|二|三|四|五|几|多|若干|所有|全部|这几|这些).{0,4}"
    r"(?:个|项|件)?(?:任务|待办|事情|事项|事|要做)|"
    r"(?:任务|待办).{0,5}(?:都|一起|批量)|"
    r"(?:批量|一起).{0,5}(?:排程|排期|安排|规划)|"
    r"\b(?:(?:multiple|all|these|several|two|three|four|\d+)\s+tasks?|tasks?\s+(?:together|all))\b",
    re.IGNORECASE,
)
_TASK_MANAGEMENT_INTENT = re.compile(
    r"(?:新增|创建|编辑|修改|更新|标记|完成|取消|删除|安排).{0,12}"
    r"(?:任务|待办|事情|事项|要做)|"
    r"(?:任务|待办).{0,8}(?:新增|创建|编辑|修改|更新|标记|完成|取消|删除)",
    re.IGNORECASE,
)
_TASK_WRITE_TOOL_NAMES = frozenset(
    {
        "create_task",
        "create_task_batch",
        "update_task",
        "change_task_state",
        "change_task_batch_state",
        "complete_task",
        "reschedule_task",
        "cancel_task",
    }
)
_CALENDAR_WRITE_TOOL_NAMES = frozenset({"mutate_events", "create_recurring_event"})
_CALENDAR_MANAGEMENT_INTENT = re.compile(
    r"(?:新增|创建|编辑|修改|更新|取消|删除).{0,8}(?:日程|日历|会议|事件)|"
    r"(?:日程|日历|会议|事件).{0,8}(?:新增|创建|编辑|修改|更新|取消|删除)",
    re.IGNORECASE,
)
_NEGATED_INTENT_PREFIX = re.compile(
    r"(?:不要|不需要|无需|别|do not|don't)\s*(?:给我|再|去)?\s*$",
    re.IGNORECASE,
)


def _has_positive_intent(pattern: re.Pattern[str], text: str) -> bool:
    return any(
        not _NEGATED_INTENT_PREFIX.search(text[max(0, match.start() - 8) : match.start()])
        for match in pattern.finditer(text)
    )


def select_tool_names(message: str) -> frozenset[str] | None:
    """Return the union of clearly matched packs, or None when intent is unclear."""

    text = message.strip()
    if not text:
        return None
    if _SENSITIVE_OR_CROSS_USER_REQUEST.search(text):
        return frozenset()
    matched = {
        pack
        for pack, patterns in _PACK_INTENTS.items()
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)
    }
    if "availability" in matched:
        matched.discard("overview")
        if _has_positive_intent(_TASK_MANAGEMENT_INTENT, text):
            matched.add("tasks")
        else:
            matched.discard("tasks")
        if not _has_positive_intent(_CALENDAR_MANAGEMENT_INTENT, text):
            matched.discard("calendar")
    if "planning_preview" in matched:
        matched.add("plan_review")
        if _has_positive_intent(_TASK_MANAGEMENT_INTENT, text):
            matched.add("tasks")
        else:
            matched.discard("tasks")
        if not _has_positive_intent(_CALENDAR_MANAGEMENT_INTENT, text):
            matched.discard("calendar")
    # Broad, cross-domain requests are safer with the full registry available.
    if not matched or len(matched) > 4:
        return None
    selected = set().union(*(PACK_TOOL_NAMES[pack] for pack in matched))
    if "tasks" in matched and not _has_positive_intent(_TASK_MANAGEMENT_INTENT, text):
        selected.difference_update(_TASK_WRITE_TOOL_NAMES)
    if "calendar" in matched and not _has_positive_intent(_CALENDAR_MANAGEMENT_INTENT, text):
        selected.difference_update(_CALENDAR_WRITE_TOOL_NAMES)
    if "plan_adaptation" in matched:
        # A single reschedule has its own approval gate. Keep unrelated task,
        # calendar and policy mutations out of a one-off conflict workflow.
        selected.difference_update(_TASK_WRITE_TOOL_NAMES)
        selected.difference_update(_CALENDAR_WRITE_TOOL_NAMES)
        selected.difference_update({"list_tasks", "list_events"})
        selected.update(
            {
                "get_current_datetime",
                "get_planning_context",
                "detect_schedule_disruptions",
                "get_task",
                "reschedule_task",
            }
        )
    if "automation_replan" not in matched:
        selected.difference_update({"list_automation_policies", "apply_local_replan"})
    return frozenset(selected)


def should_limit_to_read_tools(message: str) -> bool:
    if _VAGUE_PLANNING_REQUEST.search(message):
        return True
    has_positive_write = _has_positive_intent(_EXPLICIT_WRITE_INTENT, message)
    if _READ_ONLY_INTENT.search(message) and not has_positive_write:
        return True
    return bool(_QUERY_ONLY_INTENT.search(message)) and not has_positive_write


def is_multi_task_schedule_request(message: str) -> bool:
    return bool(_MULTI_TASK_SCHEDULE_REQUEST.search(message))
