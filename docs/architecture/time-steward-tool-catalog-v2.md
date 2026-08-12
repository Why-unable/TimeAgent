# Time Steward Tool Catalog v2

> 实现状态更新（2026-07-24）：本文件前面的内容保留了设计演进记录；当前实际暴露给
> Time Steward 的日程写入口为 `mutate_events(operations)` 和
> `create_recurring_event(...)`。`mutate_events` 的每个 `operations` 成员使用
> `action: "create" | "update" | "cancel" | "link_task"`，并可以一次承载多个相关
> 日程变更；它只产生一张 ActionProposal。单项的 `create_event`、`update_event`、
> `cancel_event`、`create_event_batch` 和 `set_event_task_link` 仍保留为内部兼容实现，
> 但不再注册给模型。任务和提醒仍保留细粒度工具，以维持低风险创建/推进与高风险撤销的
> 不同审批策略。当前 Time Steward 可见工具总数为 25。

- 状态：设计提案
- 日期：2026-07-24
- 范围：Time Steward 的模型可见工具、Briefing Handoff 和批量日程操作

## 1. 设计原则

1. 所有工具都遵循 `Tool -> Application Service -> Domain/Repository -> ORM`。
2. `actor`、`conversation_id`、`thread_id`、`agent_run_id`、权限、幂等上下文和用户偏好由
   `ToolRuntime[RuntimeContext]` 注入，不作为模型可填写参数。
3. 数据库存储 UTC；工具中的 `datetime` 必须是带时区的 RFC 3339 时间。用户时区由
   Runtime Context 明确提供。
4. 查询工具可以适度聚合；写工具按业务聚合根（日程、任务、提醒）分开。
5. 普通字段修改使用一个 Patch 工具；状态迁移与普通字段修改分离。
6. 不向 Agent 提供物理删除工具。删除意图转换为可审计、可恢复的状态迁移。
7. 高风险写工具由 `HumanInTheLoopMiddleware` 中断，并在 PostgreSQL 中建立
   `ActionProposal`；批准前不得产生业务写入。
8. 全部工具可以在 `create_agent()` 中预注册，但 middleware 每轮只向模型暴露与当前场景
   相关的工具子集。
9. 本文签名是目标契约；“演进”或“新增”工具需要在实现时同步增加 Service、风险策略、
   测试、OpenAPI（如涉及 API）和评测用例。

## 2. 共享类型与签名约定

以下类型用于描述模型可见参数。每个工具的 Python 实现还会额外接收一个对模型隐藏的
`runtime: ToolRuntime[RuntimeContext]`。

```python
from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

EntityType = Literal["event", "task", "reminder", "event_series"]
EventStateTransition = Literal["cancel", "restore"]
TaskStateTransition = Literal["start", "complete", "reopen", "cancel"]
ReminderStateTransition = Literal["cancel", "reactivate", "snooze"]
ReminderTargetType = Literal["custom", "event", "task"]
Visibility = Literal["private", "public"]


class EventPatch:
    title: str | None
    description: str | None
    start_at: datetime | None
    end_at: datetime | None
    timezone: str | None
    location: str | None
    visibility: Visibility | None


class TaskPatch:
    title: str | None
    description: str | None
    project: str | None
    priority: str | None
    due_at: datetime | None
    planned_start_at: datetime | None
    planned_end_at: datetime | None
    estimated_minutes: int | None
    tags: list[str] | None


class ReminderPatch:
    title: str | None
    trigger_at: datetime | None
    timezone: str | None
    channel: str | None


class EventDraft:
    title: str
    start_at: datetime
    end_at: datetime
    timezone: str
    description: str = ""
    location: str = ""
    visibility: Visibility = "private"
    task_id: UUID | None = None
    reminder_offsets_minutes: list[int] | None = None


class TaskDraft:
    title: str
    description: str = ""
    project: str = ""
    priority: str = "medium"
    due_at: datetime | None = None
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None
    estimated_minutes: int | None = None
    tags: list[str] | None = None
    reminder_offsets_minutes: list[int] | None = None


class VersionedTaskRef:
    task_id: UUID
    expected_version: int


class RecurrenceRuleInput:
    frequency: Literal["daily", "weekly", "monthly"]
    interval: int = 1
    weekdays: list[int] | None = None
    month_days: list[int] | None = None
    ends_on: date | None = None
    occurrence_count: int | None = None
```

Patch 字段需要保留“未提供”和“显式清空”的区别：

- 未提供字段：保持原值；
- 显式传入 `null`：仅清空允许为空的字段；
- 实现时使用 Pydantic `model_fields_set` 或等价机制识别二者；
- Application Service 仍是字段可修改性和状态约束的最终校验边界。

本文中的 `EventSummary`、`TaskSummary`、`ReminderSummary`、`BatchOperationResult` 等名称
表示结构化返回 DTO，不表示新的 ORM Model。

## 3. Runtime 注入而非工具调用

以下信息不提供对应工具：

- 当前用户和权限；
- Conversation、Thread 和 AgentRun 标识；
- 本次 Run 的固定时间锚点；
- 用户 IANA 时区和语言；
- 工作时间、睡眠时间、默认日程时长；
- 专注时间、默认提醒提前量和规划规则；
- 默认天气位置和新闻主题偏好；
- Tool Call 审计与幂等上下文。

仅在需要复核运行过程中的真实时钟时使用 `get_current_datetime`。

## 4. 基础与查询工具

### 4.1 `get_current_datetime`（现有）

```python
def get_current_datetime() -> CurrentDateTimeResult:
    """返回 Run 固定时间锚点，以及调用工具时实际观察到的 UTC/用户本地时间。"""
```

### 4.2 `get_day_overview`（新增）

```python
def get_day_overview(
    target_date: date,
) -> DayOverview:
    """返回用户时区内指定日期的日程、计划任务、截止任务和待处理提醒。"""
```

### 4.3 `get_item_details`（由三个 `get_*` 查询工具演进）

```python
def get_item_details(
    entity_type: EntityType,
    entity_id: UUID,
) -> TimeItemDetails:
    """读取一个对象的完整信息、版本号和关联对象。"""
```

这是只读工具，允许用受限的 `entity_type` 聚合日程、任务、提醒和重复日程系列查询。任何写操作
仍必须使用对象专属工具。

### 4.4 `search_events`（由 `list_events` 演进）

```python
def search_events(
    range_start: datetime | None = None,
    range_end: datetime | None = None,
    query: str | None = None,
    task_id: UUID | None = None,
    statuses: list[str] | None = None,
    limit: int = 20,
) -> list[EventSummary]:
    """按时间范围、关键词、任务关联和状态搜索当前用户的日程。"""
```

### 4.5 `search_tasks`（由 `list_tasks` 演进）

```python
def search_tasks(
    query: str | None = None,
    statuses: list[str] | None = None,
    priorities: list[str] | None = None,
    due_from: datetime | None = None,
    due_to: datetime | None = None,
    planned_from: datetime | None = None,
    planned_to: datetime | None = None,
    limit: int = 20,
) -> list[TaskSummary]:
    """按关键词、状态、优先级、截止时间和计划时间搜索任务。"""
```

### 4.6 `search_reminders`（由 `list_reminders` 演进）

```python
def search_reminders(
    query: str | None = None,
    statuses: list[str] | None = None,
    trigger_from: datetime | None = None,
    trigger_to: datetime | None = None,
    target_type: ReminderTargetType | None = None,
    target_id: UUID | None = None,
    limit: int = 20,
) -> list[ReminderSummary]:
    """按状态、触发时间和关联对象搜索提醒。"""
```

### 4.7 `find_free_slots`（现有，扩充约束）

```python
def find_free_slots(
    range_start: datetime,
    range_end: datetime,
    duration_minutes: int,
    daily_start: time | None = None,
    daily_end: time | None = None,
    working_hours_only: bool = True,
    exclude_event_id: UUID | None = None,
    max_results: int = 10,
) -> list[FreeSlot]:
    """使用日程、已规划任务、工作时间和用户时区确定性计算空闲时段。"""
```

不再把 `detect_conflicts` 作为创建日程前必须由模型主动调用的安全边界。`create_event`、
`update_event` 和批量日程 Service 必须始终自行执行冲突校验；`find_free_slots` 只负责向 Agent
提供规划候选。

## 5. 日程写工具

### 5.1 `create_event`（现有，扩充参数）

> 当前 Agent 的统一写入口 `mutate_events` / `create_recurring_event` 使用可辨识联合类型
> `time`：明确日期使用 `{kind: "absolute", start_at, end_at}`；相对表达使用
> `{kind: "relative", offset, unit, source_text, local_time?, duration_minutes}`。模型负责按语义
> 选择类型，后端只校验结构并以不可变 `AgentRun.anchor_at` 和用户 IANA 时区确定性解析，
> 不使用正则或第二次 LLM 调用猜测原句意图。未指定时长时模型从 Runtime 偏好复制默认日程
> 时长。解析记录写入 `temporal.resolved` 审计事件。详见 ADR 0021。

```python
def create_event(
    title: str,
    start_at: datetime,
    end_at: datetime,
    timezone: str,
    description: str = "",
    location: str = "",
    visibility: Visibility = "private",
    task_id: UUID | None = None,
    reminder_offsets_minutes: list[int] | None = None,
) -> EventResult:
    """创建一个日程；省略提醒策略时使用用户默认值。"""
```

### 5.2 `update_event`（新增）

```python
def update_event(
    event_id: UUID,
    expected_version: int,
    patch: EventPatch,
) -> EventResult:
    """修改日程普通字段；时间变化时由 Service 同步相对提醒。"""
```

### 5.3 `change_event_state`（由 `cancel_event` 演进）

```python
def change_event_state(
    event_id: UUID,
    expected_version: int,
    transition: EventStateTransition,
) -> EventResult:
    """取消或恢复日程，不执行物理删除。"""
```

### 5.4 `set_event_task_link`（新增）

```python
def set_event_task_link(
    event_id: UUID,
    expected_version: int,
    task_id: UUID | None,
) -> EventResult:
    """把日程关联到一个任务；task_id=null 表示解除关联。"""
```

## 6. 任务写工具

### 6.1 `create_task`（现有，扩充默认提醒语义）

```python
def create_task(
    title: str,
    description: str = "",
    project: str = "",
    priority: str = "medium",
    due_at: datetime | None = None,
    planned_start_at: datetime | None = None,
    planned_end_at: datetime | None = None,
    estimated_minutes: int | None = None,
    tags: list[str] | None = None,
    reminder_offsets_minutes: list[int] | None = None,
) -> TaskResult:
    """创建 Inbox、截止型或已规划任务；有明确时间时可自动建立相对提醒。"""
```

### 6.2 `update_task`（由 `reschedule_task` 演进）

```python
def update_task(
    task_id: UUID,
    expected_version: int,
    patch: TaskPatch,
) -> TaskResult:
    """修改任务普通字段；时间变化时由 Service 同步关联提醒。"""
```

### 6.3 `change_task_state`（由 `complete_task`、`cancel_task` 演进）

```python
def change_task_state(
    task_id: UUID,
    expected_version: int,
    transition: TaskStateTransition,
) -> TaskResult:
    """通过任务状态机开始、完成、重新打开或取消任务。"""
```

状态转换使用一个带受限枚举的领域工具，但不合并到 `update_task`。风险策略可以根据
`transition` 区分：例如 `start` 与 `reopen` 风险较低，`complete` 与 `cancel` 需要审批。

### 6.4 `create_task_batch`（新增）

```python
def create_task_batch(
    tasks: list[TaskDraft],
    operation_label: str | None = None,
) -> BatchOperationResult:
    """原子创建一组有限任务；含高影响字段时整个批次只建立一个 ActionProposal。"""
```

适用于“创建 A、B、C 三个不同任务”。第一版要求一次最少 2 项、最多 50 项，且在一个事务中
执行。纯 Inbox 任务可按低风险策略直接执行并保留一条批次审计；任一任务含计划时间、提醒策略或
其他高影响字段时，整个批次只触发一次 HITL。

### 6.5 `change_task_batch_state`（新增，高风险）

```python
def change_task_batch_state(
    items: list[VersionedTaskRef],
    transition: Literal["complete", "cancel"],
) -> BatchOperationResult:
    """原子完成或取消一批任务；整个批次只建立一个 ActionProposal。"""
```

适用于“取消 A、B、C 三个无关联任务”。每一项携带其乐观锁版本；批准后若任一任务已变化、无权
访问或不能完成/取消，则整个批次失败，不留下部分成功的业务事实。

## 7. 提醒写工具

### 7.1 `create_reminder`（现有，幂等键改为 Runtime 注入）

```python
def create_reminder(
    title: str,
    trigger_at: datetime,
    timezone: str,
    channel: str = "default",
    target_type: ReminderTargetType = "custom",
    target_id: UUID | None = None,
) -> ReminderResult:
    """创建独立提醒，或创建绑定日程/任务的提醒。"""
```

模型不再生成 `idempotency_key`。后端根据 AgentRun、Tool Call 和规范化参数生成稳定幂等键。

### 7.2 `update_reminder`（新增）

```python
def update_reminder(
    reminder_id: UUID,
    expected_version: int,
    patch: ReminderPatch,
) -> ReminderResult:
    """修改尚可编辑的提醒内容、触发时间、时区或渠道。"""
```

### 7.3 `change_reminder_state`（由 `cancel_reminder` 演进）

```python
def change_reminder_state(
    reminder_id: UUID,
    expected_version: int,
    transition: ReminderStateTransition,
    snooze_until: datetime | None = None,
) -> ReminderResult:
    """取消、重新激活或稍后提醒；snooze 时必须提供 snooze_until。"""
```

### 7.4 `set_reminder_target`（新增）

```python
def set_reminder_target(
    reminder_id: UUID,
    expected_version: int,
    target_type: ReminderTargetType,
    target_id: UUID | None = None,
) -> ReminderResult:
    """绑定任务、绑定日程，或切换为不绑定对象的 custom 提醒。"""
```

### 7.5 `set_reminder_policy`（新增）

```python
def set_reminder_policy(
    target_type: Literal["event", "task"],
    target_id: UUID,
    expected_version: int,
    offsets_minutes: list[int],
) -> ReminderPolicyResult:
    """替换一个日程或任务的相对提醒策略，并确定性同步提醒实例。"""
```

Agent 不应逐条创建“一周前、三天前、一天前、半小时前”等提醒。它只设置一次策略，
Application Service 和 Reminder Service 负责创建、移动或取消对应提醒。

## 8. 规划工具

### 8.1 `propose_schedule_plan`（新增，只读预演）

```python
def propose_schedule_plan(
    task_ids: list[UUID],
    range_start: datetime,
    range_end: datetime,
    strategy: Literal["plan_tasks_only", "create_linked_event_blocks"] = "plan_tasks_only",
    constraints: list[str] | None = None,
) -> SchedulePlan:
    """确定性生成已有任务的安排草案，不修改业务数据。"""
```

### 8.2 `apply_schedule_plan`（新增，高风险）

```python
def apply_schedule_plan(
    plan_id: UUID,
    expected_version: int,
) -> SchedulePlanResult:
    """申请原子应用已保存的计划草案；执行前进入一次 HITL。"""
```

`SchedulePlan` 必须保存规范化变更清单和版本，不能只存在于消息文本中。

`propose_schedule_plan` 不创建任务。它读取已存在的任务、空闲时间、工时、优先级和截止时间，
产生“任务 -> 时间段”的草案。`strategy="plan_tasks_only"` 只更新任务的计划区间；
`strategy="create_linked_event_blocks"` 则在批准后创建关联任务的执行日程块。两种策略都必须在
`SchedulePlan` 中逐项展示，`apply_schedule_plan` 只对应一次审批和一次原子写入。

## 9. Briefing Handoff

### 9.1 `transfer_to_briefing`（现有）

```python
def transfer_to_briefing(
    request: str,
    start_date: date | None = None,
    end_date: date | None = None,
    target_date: date | None = None,
    requested_sections: list[str] | None = None,
    locations: list[str] | None = None,
    news_topics: list[str] | None = None,
    constraints: list[str] | None = None,
    previous_briefing_run_id: str | None = None,
    previous_feedback: str | None = None,
) -> Command:
    """把简报范围、要求和反馈交给只读 Briefing Workflow。"""
```

聊天中的手动简报由该工具 Handoff；定时简报仍直接进入 Briefing Workflow，不先调用
Time Steward。

## 10. 不向 Time Steward 暴露的外部研究工具

`get_weather_forecast` 和 `search_news` 不注册到 Time Steward。它们属于 Briefing Agent 的
研究工具：

```python
def research_calendar(
    start_date: date,
    end_date: date,
) -> ResearchToolResult:
    """读取本地日期范围内的已确认/暂定日程。"""


def research_tasks(
    start_date: date,
    end_date: date,
    include_overdue: bool = True,
) -> ResearchToolResult:
    """读取日期范围相关的已计划、将到期和逾期任务。"""


def research_weather(
    start_date: date,
    end_date: date,
    location: str = "",
) -> ResearchToolResult:
    """获取已解析地点的天气；范围受用户设置和 Provider 上限约束。"""


def research_news(
    topics: list[str],
    start_at: datetime,
    end_at: datetime,
    limit: int = 12,
) -> ResearchToolResult:
    """从受支持 Feed 和主题映射中获取新闻。"""


def get_news_source_catalog() -> ResearchToolResult:
    """读取受信任 RSS 源和可用主题目录，供新闻研究前选择与纠错。"""
```

这样可以：

- 缩小 Time Steward 每轮工具 Grammar；
- 保持 Time Steward 专注于时间管理和业务写操作；
- 把天气、新闻的重试、Provider 降级和完整性检查留在 Briefing Agent；
- 避免同一 Provider 在两个 Agent 中形成两套不同调用策略。

用户在普通聊天中只询问天气或新闻时，Time Steward 可以通过 `transfer_to_briefing` 指定仅生成
对应 section。若未来产品需要独立的研究型对话，再设计专门的 Research Handoff，不复制
Provider 工具到 Time Steward。

## 11. 批量和重复日程工具

### 11.1 为什么需要

“从下周开始连续五天每天 9 点安排晨会”不应转换为五次 `create_event`。五个 Tool Call 会产生
五个独立 interrupt 和 ActionProposal，用户必须逐个审批，还会出现批准一部分后的不一致状态。

需要支持受限、可预览、幂等且原子执行的批量领域命令，但不提供任意类型的
`batch_update_items` 万能工具。

### 11.2 `create_event_batch`（新增，高风险）

```python
def create_event_batch(
    events: list[EventDraft],
    operation_label: str | None = None,
) -> BatchOperationResult:
    """原子创建一组有限日程；整个批次只建立一个 ActionProposal。"""
```

第一版约束：

- 一次最少 2 项、最多 31 项；
- 所有日程必须属于当前用户；
- 一次 Tool Call 对应一个 interrupt 和一个 ActionProposal；
- 审批卡片展示总数、日期范围、每项时间、冲突、任务关联和将生成的提醒数量；
- 批准后在一个数据库事务中重新校验并执行；
- 任一项目在批准后出现冲突或版本失效，整个批次失败，不产生部分写入；
- 批次有一个幂等键，每项使用由“批次键 + 项目序号”派生的幂等键；
- 审批支持 approve/edit/reject；编辑后必须重新校验完整批次。

### 11.3 `create_recurring_event`（新增，高风险，需要 ADR 和迁移）

“每天”“每周一三五”等长期重复要求不应展开为大量独立日程。应创建一个可管理的重复日程
系列：

```python
def create_recurring_event(
    template: EventDraft,
    recurrence: RecurrenceRuleInput,
) -> RecurringEventResult:
    """创建一个重复日程系列；整个系列只建立一个 ActionProposal。"""
```

第一版安全约束：

- `interval` 必须是正整数；
- `weekly` 才接受 `weekdays`，`monthly` 才接受 `month_days`；
- `ends_on` 和 `occurrence_count` 必须且只能提供一个；
- 第一版最多覆盖 366 天或 366 次；
- 用户没有说明结束条件时，Agent 必须追问，不得自行创建无限系列；
- 审批卡片展示重复规则、首末日期、预计次数、冲突摘要和提醒策略；
- PostgreSQL 保存系列规则与 occurrence 的关联，不能只保存一批互不关联的日程。

该能力需要新增重复日程持久化模型，实施前必须记录 ADR。未来如确有“无限重复”需求，可再使用
滚动窗口物化 occurrence，不在第一版提前实现。

### 11.4 `update_recurring_event`（新增，高风险）

```python
def update_recurring_event(
    series_id: UUID,
    expected_version: int,
    patch: EventPatch,
    scope: Literal["all", "future"],
    effective_from: date | None = None,
) -> RecurringEventResult:
    """修改全部 occurrence 或从指定日期开始的未来 occurrence。"""
```

修改单次 occurrence 仍使用 `update_event`；修改整个系列或未来部分才使用该工具。

### 11.5 `change_recurring_event_state`（新增，高风险）

```python
def change_recurring_event_state(
    series_id: UUID,
    expected_version: int,
    transition: EventStateTransition,
    scope: Literal["all", "future"],
    effective_from: date | None = None,
) -> RecurringEventResult:
    """取消或恢复整个系列，或从指定日期开始的未来部分。"""
```

### 11.6 其他批量操作

- 多任务自动排程使用 `propose_schedule_plan` + `apply_schedule_plan`，不新增通用批量修改工具；
- 批量创建任务使用 `create_task_batch`，批量完成或取消任务使用
  `change_task_batch_state`；
- 批量取消互不相关日程暂不开放；出现明确需求后，再增加专属的
  `change_event_batch_state`，每个批次仍只对应一个 ActionProposal；
- 不允许一个批量工具混合日程、任务和提醒的任意写入。

## 12. 动态工具包

所有已实现工具在 `create_agent()` 创建时预注册，`ToolPolicyMiddleware` 每轮根据 Runtime Context、
权限、对话阶段和最近工具结果筛选：

| 工具包 | 每轮可能暴露的工具 |
| --- | --- |
| 基础 | `get_current_datetime`、`get_day_overview`、`get_item_details` |
| 日程 | `search_events`、`find_free_slots`、日程单项/批量/重复系列工具 |
| 任务 | `search_tasks`、`find_free_slots`、任务写工具 |
| 提醒 | `search_reminders`、提醒写工具和提醒策略工具 |
| 规划 | 三类搜索、`find_free_slots`、`propose_schedule_plan`、`apply_schedule_plan` |
| 简报 | `transfer_to_briefing` |
| 只读运行 | 仅基础、查询、规划预演和 Handoff 工具 |

工具选择 middleware 只做能力裁剪，不根据关键词代替 Agent 推理，也不能绕过 Application Service
权限校验。

## 13. HITL 风险建议

| 操作 | 建议风险 |
| --- | --- |
| 查询、空闲时间和计划预演 | read，无审批 |
| 创建普通 Inbox 任务、修改非时间型说明 | low，直接执行并审计 |
| 创建/修改日程、修改计划时间、修改提醒策略 | high，审批 |
| 完成或取消任务、取消提醒、变更关联 | high，审批 |
| 批量创建、应用计划、重复日程系列操作 | high，一批一次审批 |
| 物理删除、跨用户、任意混合批量写入 | 不注册 |

风险判断不仅看工具名称，还应检查受限枚举和参数。例如 `change_task_state(start)` 可以是低风险，
而 `change_task_state(cancel)` 必须审批。

## 14. 工具数量

本文的目标契约中：

| Agent | 工具数量 | 说明 |
| --- | ---: | --- |
| Time Steward | 28 | 基础/查询 7，日程 4，任务 5，提醒 5，规划 2，Briefing Handoff 1，批量与重复日程 4。天气与新闻研究工具不计入此处。 |
| Briefing Agent | 5 | 当前为 `research_calendar`、`research_tasks`、`research_weather`、`research_news`、`get_news_source_catalog`。只读，不具备业务写入能力。 |
| 合计 | 33 | 两个 Agent 的模型可见工具总数；实际每轮会通过 middleware 暴露其中很小的相关子集。 |

当前代码中的工具注册数为 34：Time Steward 29 个、Briefing Agent 5 个。已落地的 v2 增量包括
`update_event`、`set_event_task_link`、`create_event_batch`、`update_task`、`create_task_batch`、
`change_task_state`、`change_task_batch_state`、`update_reminder`、`set_reminder_target`、
`create_recurring_event`、`propose_schedule_plan` 和 `apply_schedule_plan`；批量工具为一次 Tool Call /
一次审批 / 一个数据库事务。
上表的 33 个仍是完整目标数：重复日程系列、提醒编辑/策略、任务批量状态变更与持久化排程草案要和各自的
领域模型、迁移和 ADR 一起交付，不能用表面工具占位。

## 15. 官方文档依据

- [LangChain Tools / Dynamic tool selection](https://docs.langchain.com/oss/python/langchain/tools#dynamic-tool-selection)
- [Custom middleware / Dynamically selecting tools](https://docs.langchain.com/oss/python/langchain/middleware/custom#dynamically-selecting-tools)
- [LangChain Runtime / Middleware context](https://docs.langchain.com/oss/python/langchain/runtime#inside-middleware)
- [LangChain Handoffs](https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs)
