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
    "clock": (
        r"(?:现在|当前|此刻).{0,6}(?:几点|时间)|几点了|现在几时|今天(?:的)?(?:日期|几号)|"
        r"\b(?:what time is it|current time|what is today's date|what is the date today)\b",
    ),
    "planning_preview": (
        r"(?:创建|生成|提出).{0,32}(?:排程|日程|计划|草案)|(?:排程|日程|计划|草案).{0,32}(?:创建|生成|提出)|"
        r"排期|排程|排到|排入|排下|规划|计划一下|帮我安排|安排(?:一下|任务|这些|课程|工作)|"
        r"安排.{0,20}(?:任务|待办|事情|事项|要做|工作)|"
        r"(?:任务|待办|事项|工作|项目).{0,20}(?:安排|排程|排期|排入|排到|规划|分散)|"
        r"(?:安排|排程|排期|规划).{0,16}(?:任务|待办|事项|工作|项目|日程|阶段)|"
        r"(?:本周|下周|未来几周|接下来几周).{0,16}(?:安排|分散|排程|排期)|"
        r"\bschedule\s+(?:(?:these|all|some)\s+)?"
        r"(?:(?:two|three|four|several|multiple|some|\d+)\s+)?tasks?\b|\bplanning\b",
    ),
    "plan_comparison": (
        r"(?:比较|对比|权衡).{0,16}(?:排程|方案|安排|计划)|"
        r"(?:排程|方案|安排|计划).{0,10}(?:比较|对比)|"
        r"\bcompare\b.{0,20}\bplans?\b",
    ),
    "plan_review": (
        r"(?:应用|执行|批准|审批|编辑|修改|调整|验证|校验|放弃).{0,24}(?:排程|计划|草案)|"
        r"(?:排程|计划|草案).{0,80}(?:应用|执行|批准|审批|编辑|修改|调整|改到|改为|验证|校验|放弃)|"
        r"\b(?:apply|approve|edit|validate|abandon)\b.{0,24}\b(?:schedule\s+)?plans?\b",
    ),
    "duration_guidance": (
        r"估(?:时|算)|(?:建议|推荐|预计|预估).{0,10}(?:时长|用时|多久)|"
        r"(?:需要|大概|大约).{0,10}(?:多久|多长时间)|"
        r"\b(?:estimate (?:the )?duration|how long|duration estimate)\b",
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
        r"洞察|时间偏好|时间习惯|专注时间|作息|估时|估算时长|实际做了多久|工作量|容量|记忆|记住|记下|忘记|习惯规律|"
        r"(?:能|可以|是否能|是否可以).{0,8}(?:塞进|放进|安排进|放下|挤进)|"
        r"估时.{0,8}(?:太短|偏短|过长|太长|准确|不准确)|(?:太短|偏短|过长|太长|准确|不准确).{0,8}估时|"
        r"estimate.{0,20}(?:too short|too long|accurate|inaccurate)|"
        r"\b(?:insights?|remember|memorize|forget|time preferences?|work habits?|"
        r"duration estimate|capacity forecast|fit(?: into)? (?:today|this week)|"
        r"can it fit|will it fit)\b",
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
_STRICT_READ_ONLY_INTENT = re.compile(
    r"只(?:看|查|读|分析|给建议|要建议)|只给.{0,4}建议|只是查询|保持(?:原样|不变)|"
    r"\bread.only\b|\bno changes?\b",
    re.IGNORECASE,
)
_NO_CHANGES_ANYTHING_INTENT = re.compile(
    r"(?:不要|不做|不得|do not|don't)\s*(?:(?:进行|做|make)\s*)?"
    r"(?:任何\s*)?(?:修改|变更|改动|操作|changes?|modifications?)"
    r"\s*(?:任何(?:东西|内容|事情)?|anything(?: at all)?)?",
    re.IGNORECASE,
)
_QUERY_ONLY_INTENT = re.compile(
    r"看看|看一下|查看|查询|列出|告诉我|是什么|有哪些|有什么|有啥|什么是|为什么|为何|哪里|"
    r"是否|有没有|吗[？?]|\?|\b(?:show|list|check|explain|what is|how many)\b",
    re.IGNORECASE,
)
_EXPLICIT_WRITE_INTENT = re.compile(
    r"创建|新增|添加|设置|保存|修改|改动|改到|改为|改成|改期|移动|挪到|提前|延后|调整|"
    r"安排|排在|排到|排程|排期|重排|取消|删除|应用|执行|记住|记下|忘记|提醒我|"
    r"(?:估时|时长建议).{0,8}(?:太短|偏短|过长|太长|准确|不准确)|"
    r"(?:太短|偏短|过长|太长|准确|不准确).{0,8}(?:估时|时长建议)|"
    r"estimate.{0,20}(?:too short|too long|accurate|inaccurate)|"
    r"\b(?:create|add|set|save|change|move|reschedule|cancel|delete|apply)\b|"
    r"\bschedule\s+(?:(?:these|all|some)\s+)?"
    r"(?:(?:two|three|four|several|multiple|some|\d+)\s+)?tasks?\b",
    re.IGNORECASE,
)
_EXPLICIT_MEMORY_WRITE_INTENT = re.compile(
    r"\b(?:please\s+)?(?:remember|memorize)\s+(?:that|my|this)\b|"
    r"\b(?:please\s+)?(?:forget|save|store|update|change|delete)\s+(?:my|the)\s+"
    r"(?:(?:time|schedule|work|planning)\s+)?(?:preferences?|habits?|routines?|memories)\b",
    re.IGNORECASE,
)
_MEMORY_LOOKUP_QUESTION = re.compile(r"\b(?:do|did)\s+you\s+(?:remember|forget)\b", re.IGNORECASE)
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
_PLAN_INTERACTION_REQUEST = re.compile(
    r"(?:打开|开启|展示|提供|请求|调出).{0,32}"
    r"(?:优先顺序|排序|时间线).{0,8}(?:交互|控件|组件)|"
    r"(?:计划|草案).{0,80}(?:打开|开启|展示|提供|请求|调出).{0,32}"
    r"(?:优先顺序|排序|时间线).{0,8}(?:交互|控件|组件)",
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
_ORDERED_TASK_SEQUENCE = re.compile(
    r"(?:先|首先).{0,160}(?:再|然后|之后|最后)|"
    r"(?:再|然后|之后).{0,120}(?:最后|后续|完成)|"
    r"[^。]{0,100}[，,].{0,80}(?:再|然后|之后)",
    re.IGNORECASE,
)
_SCHEDULE_TIME_CONSTRAINT = re.compile(
    r"(?:每天|每日).{0,12}(?:最多|不超过).{0,12}(?:分钟|小时)|"
    r"至少.{0,12}(?:分|安排|用).{0,10}(?:\d+|[一二三四五六七八九十]+)\s*(?:个)?(?:工作日|天)|"
    r"(?:不排|不安排|只排).{0,5}(?:周末|周六|周日|工作日)",
    re.IGNORECASE,
)
_SCHEDULE_GOAL_LANGUAGE = re.compile(
    r"我想|我打算|我需要|需要完成|需完成|帮我|请帮我|想把|需要把|要把|"
    r"想分.{0,8}(?:几次|多次|几天|几周)",
    re.IGNORECASE,
)
_TASK_MANAGEMENT_INTENT = re.compile(
    r"(?:新增|创建|编辑|修改|更新|标记|完成|取消|删除|安排).{0,12}"
    r"(?:任务|待办|事情|事项|要做)|"
    r"(?:任务|待办).{0,8}(?:新增|创建|编辑|修改|更新|标记|完成|取消|删除|"
    r"改到|改为|改期|调整|挪到|提前|延后|重排)",
    re.IGNORECASE,
)
_TASK_LOOKUP_INTENT = re.compile(
    r"任务列表|(?:查找|搜索|列出|查看).{0,8}(?:任务|待办)|"
    r"(?:任务|待办).{0,8}(?:标题|名称).{0,8}(?:查找|搜索|匹配)|"
    r"\b(?:list|find|search)\s+tasks?\b",
    re.IGNORECASE,
)
_TASK_RECORD_MUTATION_INTENT = re.compile(
    r"(?:新增|创建|编辑|修改|更新|标记|完成|取消|删除|改到|改为|改期|调整|挪到|提前|延后|重排).{0,12}"
    r"(?:任务|待办|事情|事项|要做)|"
    r"(?:任务|待办|事情|事项|要做).{0,10}"
    r"(?:新增|创建|编辑|修改|更新|标记|完成|取消|删除|改到|改为|改期|调整|挪到|提前|延后|重排)|"
    r"\b(?:create|add|update|edit|complete|cancel|delete|reschedule)\s+tasks?\b",
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
    r"(?:新增|创建|添加|编辑|修改|更新|取消|删除).{0,32}(?:日程|日历|会议|事件)|"
    r"(?:日程|日历|会议|事件).{0,32}(?:新增|创建|添加|编辑|修改|更新|取消|删除)",
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


def is_explicit_plan_interaction_request(message: str) -> bool:
    """Recognize a user's direct request to open a typed control for a draft."""

    return bool(_PLAN_INTERACTION_REQUEST.search(message))


def _has_constraint_driven_schedule_intent(message: str) -> bool:
    """Recognize a structured task plan even without an explicit schedule verb."""

    return bool(
        _SCHEDULE_GOAL_LANGUAGE.search(message)
        and _ORDERED_TASK_SEQUENCE.search(message)
        and _SCHEDULE_TIME_CONSTRAINT.search(message)
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
    plan_interaction_request = is_explicit_plan_interaction_request(text)
    if plan_interaction_request:
        matched.add("plan_review")
    if _has_constraint_driven_schedule_intent(text):
        matched.add("planning_preview")
    if "plan_comparison" in matched:
        matched.update({"planning_preview", "plan_review"})
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
        if _has_positive_intent(_TASK_MANAGEMENT_INTENT, text) or _TASK_LOOKUP_INTENT.search(text):
            matched.add("tasks")
        else:
            matched.discard("tasks")
        if not _has_positive_intent(_CALENDAR_MANAGEMENT_INTENT, text):
            matched.discard("calendar")
    if not matched or len(matched) > 4:
        return None
    selected = set().union(*(PACK_TOOL_NAMES[pack] for pack in matched))
    if plan_interaction_request:
        # Opening a draft control persists a typed interaction artifact. Keep
        # this explicit low-risk request separate from Apply and other writes.
        selected.intersection_update({"request_plan_interaction"})
    if "tasks" in matched and not _has_positive_intent(_TASK_MANAGEMENT_INTENT, text):
        selected.difference_update(_TASK_WRITE_TOOL_NAMES)
    if "calendar" in matched and not _has_positive_intent(_CALENDAR_MANAGEMENT_INTENT, text):
        selected.difference_update(_CALENDAR_WRITE_TOOL_NAMES)
    if "plan_adaptation" in matched:
        selected.difference_update(_TASK_WRITE_TOOL_NAMES)
        selected.difference_update(_CALENDAR_WRITE_TOOL_NAMES)
        selected.difference_update({"list_tasks", "list_events"})
        selected.update(
            {
                "get_planning_context",
                "detect_schedule_disruptions",
                "get_task",
                "reschedule_task",
            }
        )
    if "automation_replan" not in matched:
        selected.difference_update({"list_automation_policies", "apply_local_replan"})
    return frozenset(selected)


def is_sensitive_or_cross_user_request(message: str) -> bool:
    """Deterministically identify requests that must receive no business tools."""

    return bool(_SENSITIVE_OR_CROSS_USER_REQUEST.search(message.strip()))


def should_limit_to_read_tools(message: str) -> bool:
    if is_explicit_plan_interaction_request(message):
        return False
    if _VAGUE_PLANNING_REQUEST.search(message):
        return True
    if _STRICT_READ_ONLY_INTENT.search(message):
        return True
    if _NO_CHANGES_ANYTHING_INTENT.search(message):
        return True
    if _has_constraint_driven_schedule_intent(message):
        return False
    has_positive_write = _has_positive_intent(_EXPLICIT_WRITE_INTENT, message) or (
        not _MEMORY_LOOKUP_QUESTION.search(message)
        and _EXPLICIT_MEMORY_WRITE_INTENT.search(message) is not None
    )
    if _READ_ONLY_INTENT.search(message) and not has_positive_write:
        return True
    if not has_positive_write:
        return True
    return False


def is_multi_task_schedule_request(message: str) -> bool:
    return bool(_MULTI_TASK_SCHEDULE_REQUEST.search(message))


def has_explicit_task_record_mutation(message: str) -> bool:
    """Identify CRUD/reschedule intent separately from drafting a schedule plan."""

    return _has_positive_intent(_TASK_RECORD_MUTATION_INTENT, message)
