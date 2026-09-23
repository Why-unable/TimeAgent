# Time Steward 工具集核实与优化讨论

## 1. 文档状态

- 核实日期：2026-09-16
- 核实分支：`main`
- 核实提交：`29bef7a`
- 本文只记录工具集现状、问题和优化方案；本次没有修改 Agent 或业务代码。

本文以实际注册表为准，不以历史文档、旧函数定义或模型回答中的工具名称为准。

## 2. 核实结论

Time Steward 当前通过 `TIME_STEWARD_TOOLS` 向 `create_agent()` 注册：

| 分类 | 数量 |
|---|---:|
| 注册表标记为只读的业务 Tool | 19 |
| Handoff Tool | 1 |
| 写入 Tool | 24 |
| 合计 | **44** |

44 个名称全部唯一，没有重复注册。这里的“只读”是当前注册表的分类，不代表每个函数都完全没有持久化副作用；见第 5.2 节。实际核验命令为：

```bash
cd backend
DJANGO_SETTINGS_MODULE=config.settings.test \
  uv run python -c '
import django
django.setup()
from apps.agents.tools import TIME_STEWARD_TOOLS, READ_ONLY_TOOLS, WRITE_TOOLS
names = [tool.name for tool in TIME_STEWARD_TOOLS]
print(len(names), len(READ_ONLY_TOOLS), len(WRITE_TOOLS), len(set(names)))
print(names)
'
```

注册入口：

- [`backend/apps/agents/tools/__init__.py`](../../backend/apps/agents/tools/__init__.py)
- [`backend/apps/agents/agents/time_steward.py`](../../backend/apps/agents/agents/time_steward.py)

模型不会填写 `runtime: ToolRuntime[RuntimeContext]`。该参数由 LangChain 注入，包含当前用户、时区、运行时间锚点、request ID、AgentRun 和 Store 等可信运行上下文。

## 3. 当前注册清单

### 3.1 时间与交接

| 类型 | Tool | 作用 |
|---|---|---|
| 只读 | `get_current_datetime` | 返回本轮时间锚点、当前时间、用户本地时间、时区和 locale。 |
| Handoff | `transfer_to_briefing` | 将简报请求交给只读 Briefing Workflow，不直接处理简报数据。 |

### 3.2 Event 日程：4 个

| 类型 | Tool | 作用 |
|---|---|---|
| 只读 | `list_events` | 按时间范围和状态查询用户日程。 |
| 只读 | `get_event` | 查询单条日程及其版本。 |
| 写入 | `mutate_events` | 原子执行一个或多个 create/update/cancel/link_task 操作。 |
| 写入 | `create_recurring_event` | 创建有限次数的重复日程。 |

### 3.3 Task 任务：11 个

| 类型 | Tool | 作用 |
|---|---|---|
| 只读 | `list_tasks` | 按状态、截止时间查询任务。 |
| 只读 | `get_task` | 查询单任务详情和版本。 |
| 只读 | `get_task_execution_summary` | 查询计划、预计、实际执行时间及偏差。 |
| 写入 | `create_task` | 创建单个任务。 |
| 写入 | `create_task_batch` | 原子批量创建任务。 |
| 写入 | `update_task` | 修改任务属性，不改变生命周期状态。 |
| 写入 | `change_task_state` | 修改单任务状态。 |
| 写入 | `change_task_batch_state` | 原子修改多个任务状态。 |
| 写入 | `complete_task` | 完成任务并记录执行信号。 |
| 写入 | `reschedule_task` | 修改单任务 planned time，不创建 CalendarEvent。 |
| 写入 | `cancel_task` | 软取消任务并保留历史。 |

### 3.4 Reminder 提醒：6 个

| 类型 | Tool | 作用 |
|---|---|---|
| 只读 | `list_reminders` | 查询提醒列表。 |
| 只读 | `get_reminder` | 查询单条提醒。 |
| 写入 | `create_reminder` | 创建可幂等的提醒，可关联任务或日程。 |
| 写入 | `update_reminder` | 修改待发送提醒。 |
| 写入 | `set_reminder_target` | 设置或清除提醒绑定的任务/日程。 |
| 写入 | `cancel_reminder` | 取消尚未发送的提醒。 |

提醒触发和投递不由 Agent 执行，而是由 Reminder、Celery Dispatcher 和 Notification Provider 完成。

### 3.5 Planning：10 个

| 类型 | Tool | 作用 |
|---|---|---|
| 只读 | `find_free_slots` | 根据工作时间、日程和计划任务计算空闲时段。 |
| 只读 | `propose_schedule_plan` | 创建持久化排程草案，不改变任务或日程事实。 |
| 只读 | `compare_schedule_plans` | 生成两套确定性候选方案进行比较。 |
| 只读 | `detect_schedule_disruptions` | 检测计划任务与当前日程的事实重叠。 |
| 只读 | `list_automation_policies` | 查询用户允许自动重排的范围。 |
| 写入 | `validate_schedule_plan` | 用最新事实复核排程草案。 |
| 写入 | `set_schedule_plan_item_lock` | 锁定或解锁草案中的任务。 |
| 写入 | `abandon_schedule_plan` | 放弃排程草案。 |
| 写入 | `apply_schedule_plan` | 原子应用已审核的排程草案。 |
| 写入 | `apply_local_replan` | 在策略、移动数量和时间范围约束下执行可撤销局部重排。 |

### 3.6 个性化决策：3 个

| 类型 | Tool | 作用 |
|---|---|---|
| 只读 | `recommend_task_duration` | 根据历史执行证据推荐任务时长。 |
| 只读 | `get_capacity_forecast` | 计算指定时间范围的容量和风险。 |
| 写入 | `record_task_duration_feedback` | 记录用户认为估时过短、过长或准确的反馈。 |

### 3.7 外部日历、洞察与 Memory：8 个

| 类型 | Tool | 作用 |
|---|---|---|
| 只读 | `list_calendar_sync_status` | 查询只读外部日历连接状态，不返回凭据。 |
| 只读 | `list_temporal_insights` | 扫描并读取当前有效的时间风险洞察。 |
| 只读 | `get_temporal_insight` | 查询单条洞察及事实证据。 |
| 写入 | `act_on_temporal_insight` | 对洞察执行 snooze、dismiss、action 或纠正。 |
| 只读 | `search_time_memories` | 查询当前用户已确认且未过期的长期时间偏好。 |
| 写入 | `remember_time_preference` | 通过 Memory Policy 提议保存长期偏好。 |
| 写入 | `update_time_preference` | 通过 Memory Policy 提议修改长期偏好。 |
| 写入 | `forget_time_preference` | 通过 Memory Policy 提议忘记长期偏好。 |

## 4. 当前运行边界

注册到 `TIME_STEWARD_TOOLS` 不等于每次运行都把 44 个 Tool 暴露给模型：

1. `ToolPolicyMiddleware` 在只读模式下只保留只读和 Handoff Tool；读写模式才加入写 Tool。
2. Memory Tool 还受 `agent_search_tool_enabled` 和 `agent_write_tools_enabled` 控制。
3. 高风险 Tool 由 `HumanInTheLoopMiddleware` 中断，生成 `ActionProposal`，用户确认后恢复同一个 Agent thread。
4. `ToolAuditMiddleware` 记录开始、完成、失败、参数和结果，并按 Tool 类型区分 read、low、high 风险。
5. 只有只读 Tool 默认进入 Tool Retry；非幂等写 Tool 不自动重试。
6. Model/Tool call limit、错误处理、模型重试和 fallback 由 middleware 控制。

相关实现：

- [`backend/apps/agents/middleware.py`](../../backend/apps/agents/middleware.py)
- [`backend/apps/action_proposals/risk_policy.py`](../../backend/apps/action_proposals/risk_policy.py)

## 5. 核实后发现的问题

### 5.1 注册表和风险策略存在旧名称漂移

当前 `HIGH_RISK_TOOL_POLICIES` 中存在 4 个未注册的旧 Event Tool：

```text
create_event
create_event_batch
update_event
cancel_event
```

当前注册表使用的是 `mutate_events` 和 `create_recurring_event`。旧函数仍存在于 `event_tools.py`，但没有进入 `EVENT_WRITE_TOOLS`，因此不会被当前 Time Steward 直接调用。

这不一定会立刻造成运行错误，但会造成三个问题：

- 风险策略无法从注册表自动推导，容易遗漏或保留过期规则；
- 工具审计中可能出现“策略存在但 Tool 不可用”的困惑；
- 后续维护者难以判断旧函数是兼容代码、候选代码还是应该删除的代码。

建议增加注册表—风险策略契约测试，并明确把旧策略标为 legacy 或删除；禁止静默保留两套 Event Tool 心智模型。

### 5.2 只读分类中存在持久化副作用

当前有两个 Tool 的注册分类与实际行为不完全一致：

- `propose_schedule_plan` 位于 `PLANNING_READ_TOOLS`，但会通过 `PlanningService.propose_schedule_plan` 持久化一个 `SchedulePlan` 草案；它不改变 Task 或 CalendarEvent，但仍然会写入业务侧的规划事实。
- `list_temporal_insights` 位于 `INSIGHT_READ_TOOLS`，但调用 `TemporalInsightService.scan`；扫描会创建、刷新或过期 `TemporalInsight`，随后才读取开放洞察。

这两个 Tool 可以继续免 HITL，但不应在权限、审计和指标中被当作纯查询。建议把能力分类拆成 `read`、`derive_or_draft`、`write`、`handoff`，并为“读取过程中允许幂等派生写入”的 Tool 单独记录副作用类型。

### 5.3 44 个 Tool 同时构成较大的模型选择空间

当前 middleware 主要按“只读/写入/Memory 开关”过滤，没有按用户意图进一步拆分领域 Tool Pack。一个普通的“查今天安排”请求，理论上仍可能看到任务、提醒、Planning、Memory、洞察和 Handoff 等多个领域的 Schema。

可能的影响：

- Tool Schema 占用上下文 Token；
- 相近 Tool 之间选择困难，例如 `reschedule_task`、`apply_schedule_plan`、`apply_local_replan`；
- 模型先读取多个领域再回到真正目标，增加延迟；
- 同一事实被多个列表 Tool 重复查询。

### 5.4 多任务排程容易退化成逐任务写入

本次真实演练中，Agent 先放弃旧草案，再连续调用 7 次 `reschedule_task`。这说明当前 Agent 可能在已经拥有 `SchedulePlan` 的情况下，绕过 `apply_schedule_plan`，把批量排程退化为多个单任务写操作。

问题包括：

- 调用次数更多，模型和网络开销更大；
- 每个任务分别提交，缺少批量级原子性；
- 中途失败时可能出现部分任务已移动、部分任务未移动；
- `reschedule_task` 没有 `expected_version` 或 operation ID 参数；
- 该 Tool 本身只校验时间区间，不负责完整的事件/任务全局冲突校验。

当前更可靠的路径应是：

```text
propose_schedule_plan
    -> validate_schedule_plan
    -> 用户确认
    -> apply_schedule_plan
```

`reschedule_task` 应主要保留给单任务的明确移动；多任务移动应统一走 Plan Apply 或一个具备批量事务语义的专用 Tool。

### 5.5 写入 Tool 的风险分层不够显式

`risk_policy.py` 只为部分高风险 Tool 配置 HITL。其余写 Tool 会被审计为 low risk，但“写入事实”和“低风险”不是同一个维度。

按当前代码比较，24 个已注册写入 Tool 中有 11 个没有显式 `HIGH_RISK_TOOL_POLICIES` 条目；这可以是有意的低风险设计，但目前没有一份独立的 capability matrix 说明为什么它们可以不确认。与此同时，风险策略还保留了 4 个未注册的旧 Event Tool 名称。两边合在一起，容易让“未配置”被误解为“低风险”。

建议把以下属性拆开记录：

- 是否改变业务事实；
- 是否影响未来计划；
- 是否可撤销；
- 是否需要当前用户确认；
- 是否支持幂等重试；
- 是否允许批量操作。

这样 `reschedule_task`、`record_task_duration_feedback`、`act_on_temporal_insight` 等 Tool 就不会只剩一个 low/high 标签。

### 5.6 列表 Tool 的返回规模没有统一治理

`search_time_memories` 有 `limit`，但任务、日程和提醒列表的分页、上限和摘要策略不完全统一。数据量增长后，列表结果会直接进入模型上下文，增加 Token 和延迟。

优化方向：

- 为列表 Tool 统一 `limit`、游标和时间范围约束；
- 默认返回面向决策的摘要字段，详情按 ID 二次读取；
- 对任务、日程、提醒明确区分“今日摘要”和“完整列表”；
- 记录返回条数、结果 Token 和截断次数。

### 5.7 工具参数的领域类型仍有不一致

部分输入已经使用 `Literal`、Pydantic 模型和 `extra="forbid"`，但仍有 `status`、`frequency`、`target_type`、`action` 等字符串参数直接进入 Tool。

建议逐步改为：

- 领域枚举或受限 Literal；
- 批量输入统一的 Pydantic DTO；
- 对相对时间统一使用明确的时间结构，而不是让不同 Tool 各自解释字符串；
- 对更新和取消强制要求版本字段，避免模型使用过期对象。

## 6. 优化方案与优先级

### P0：先修一致性和批量写入

1. **建立 Tool Manifest 测试**：自动输出 44 个注册名称、只读/写入分类和来源模块；注册重复、未分类或风险策略孤儿名称时失败。
2. **清理 Event 旧 Tool 策略**：明确 `create_event`、`create_event_batch`、`update_event`、`cancel_event` 是 legacy 还是彻底移除，不能同时维护两套注册心智模型。
3. **修正副作用分类**：把 `propose_schedule_plan`、`list_temporal_insights` 从纯只读分类中标出，明确 draft/derive 行为的审计、幂等和权限语义。
4. **规范多任务排程路径**：多任务安排必须使用 `SchedulePlan` 的 propose/validate/apply；禁止 Agent 在同一意图中连续调用多个 `reschedule_task`。
5. **补充单任务重排的并发保护**：为 `reschedule_task` 增加 expected version 和稳定 operation ID，或将单任务移动也纳入可审计的 Change Batch。
6. **增加批量排程回归测试**：覆盖中途失败、重复确认、版本冲突、部分任务冲突、审批恢复和最终全部回滚。

### P1：降低 Tool 选择和上下文成本

1. **按意图提供 Tool Pack**：查询今日、编辑日程、安排任务、设置提醒、管理 Memory、生成简报只暴露必要领域；保留同一 Tool 名称和 Service 边界。
2. **统一列表分页和摘要返回**：先用指标证明结果规模和 Token 成本，再决定是否增加聚合查询 Tool，避免创建没有实际收益的空抽象。
3. **收紧参数 Schema**：把高频字符串参数改成枚举/限定值，批量输入统一 `extra="forbid"`，明确时间和版本字段。
4. **分离业务写入风险与审批策略**：建立可审计的 Tool Capability Matrix，而不是只依赖是否出现在 `HIGH_RISK_TOOL_POLICIES`。
5. **把 Handoff 独立于普通只读 Tool**：`transfer_to_briefing` 是控制流操作，不应和 `list_tasks`、`list_events` 一起被理解为普通查询工具。

### P2：用数据决定更复杂的优化

1. 只有在指标证明重复读取明显时，才增加 `get_planning_context` 等聚合读取能力。
2. 只有在批量排程场景无法由 `apply_schedule_plan` 覆盖时，才增加独立 `reschedule_task_batch`。
3. 只有在真实模型轨迹证明工具选择仍不稳定时，才调整工具描述、拆分 Tool Pack 或增加确定性预路由。
4. 不在当前阶段引入多 Agent、微服务、向量数据库或没有实际消费方的抽象层。

## 7. 应增加的观测指标

工具集优化不能只看“Tool 数量”。建议按 AgentRun 记录并汇总：

- 每次请求的 Tool 调用总数、读调用数、写调用数；
- 首次成功 Tool 选择率和参数校验失败率；
- 重复读取同一领域事实的比例；
- 单任务重排与批量 Plan Apply 的占比；
- Tool Schema、Tool 结果和历史消息造成的输入 Token；
- Tool p50/p95 延迟及排队、模型、审批、数据库、Provider 分段耗时；
- 高风险审批等待时间，不能与 Tool 执行时间混为一谈；
- 写入失败后的部分提交率、恢复成功率和幂等冲突率；
- 计划应用后的冲突率、撤销率、用户修改率和任务完成率。

这组指标也能验证此前“20 多次 Tool 导致接近一分钟”的判断：工具执行耗时、模型多轮耗时和 HITL 等待必须分别统计。

## 8. 建议验收顺序

1. 先添加 44 Tool 注册清单和风险策略一致性测试。
2. 再修正多任务排程必须走 `apply_schedule_plan` 的 Agent 轨迹测试。
3. 为 `reschedule_task` 增加版本、幂等和失败恢复测试。
4. 在固定数据集上比较当前全量 Tool、按意图 Tool Pack 和批量排程三种路径的调用数、Token、p95 和任务成功率。
5. 只有实验确认收益后，才落地聚合读取或进一步拆分工具。

## 9. 当前不应做的事情

- 不因为 Tool 数量达到 44 就机械删除功能；其中很多是业务边界和安全边界。
- 不把所有 Tool 合并成一个巨大 `execute_action`，否则会损失 Schema 约束、审计和风险判断。
- 不让 Agent 直接访问 ORM 或绕过 Application Service。
- 不让 LLM 自己执行提醒派发、容量数学或冲突判断。
- 不把所有写 Tool 都改成强制 HITL；应根据副作用、可撤销性和用户偏好分层。
- 不在没有调用轨迹和 Token 数据前声称 Tool Pack 已经降低延迟。

## 10. 结论

当前 44 个 Tool 的主要问题不是“数量太多”本身，而是：

1. 注册表、旧函数和风险策略存在漂移；
2. “只读”分类中仍有草案持久化和洞察扫描等派生写入；
3. 多任务排程仍可能退化为逐任务写入；
4. 单任务重排的版本和幂等保护不足；
5. Tool 暴露、返回规模和参数类型尚未完全按意图治理；
6. 缺少把工具执行、模型多轮和 HITL 等待分开的性能证据。

优先级应是先修一致性、批量事务、版本幂等和观测，再根据真实轨迹决定是否减少模型可见 Tool 数量。
