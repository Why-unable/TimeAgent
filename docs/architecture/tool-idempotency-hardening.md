# Tool 幂等现状与补强方案

- 状态：现状审计与后续实施方案
- 日期：2026-09-03
- 范围：Time Steward 注册的 Tool、HITL 恢复、Application Service 与 PostgreSQL 持久化

## 1. 目的与术语

本文说明当前 TimeAgent 在 Tool 重试、Agent 恢复和并发执行时如何避免重复副作用，以及仍需补齐
哪些边界。它不把乐观锁、状态机防重和 Tool Call 回放混称为严格业务幂等。

需要区分三种身份：

| 身份 | 当前载体 | 含义 |
|---|---|---|
| 请求身份 | `AgentRun.request_id` | 一次 HTTP/客户端请求的关联标识 |
| 逻辑操作身份 | `AgentRun.operation_id`，少数领域另有 `operation_id` | 一次希望只生效一次的业务意图 |
| 技术调用身份 | LangChain `tool_call_id` | 模型在某一轮生成的一次 Tool Call |

严格业务幂等要求相同逻辑操作即使产生不同 `tool_call_id`，也只能形成一次业务结果；不同逻辑操作
即使参数相同，也应允许分别执行。按参数永久去重会错误合并用户有意创建的同名任务或重复日程，
不能作为通用方案。

## 2. `version` 与 `expected_version`

`version` 是 PostgreSQL 业务表中的持久化字段：

- `CalendarEvent.version`：`PositiveIntegerField(default=1)`；
- `Task.version`：`PositiveIntegerField(default=1)`；
- Reminder、SchedulePlan 等可变资源也有各自版本字段。

`expected_version` 不是数据库表字段，而是更新命令的输入参数。它表示“调用方读取该对象时看到的
版本”。Tool 通常先读取对象及其 `version`，再把该值作为 `expected_version` 提交更新。

以日程更新为例：

```text
读取 Event(id=E, version=3)
  -> update_event(event_id=E, expected_version=3, changes=...)
  -> 事务内 SELECT FOR UPDATE
  -> 比较数据库 current version 与 expected version
  -> 相等：更新并把 version 改为 4
  -> 不相等：抛出 EventVersionConflictError
```

因此，同一旧参数被重复执行时，第一次把版本从 `3` 更新到 `4`，第二次仍携带
`expected_version=3`，与当前 `4` 不一致，通常会被拒绝。Task 更新采取相同机制。

这属于**乐观并发控制**，主要防止旧快照覆盖新数据；它并不等同于完整幂等：

- 第二次调用得到的是版本冲突，而不是第一次成功结果的重放；
- 如果模型在恢复后重新读取 `version=4`，再以相同内容更新，校验仍可能通过并产生新版本；
- Create 操作没有既有资源版本，无法依靠 `expected_version` 防止重复创建；
- `reschedule_task`、部分状态操作没有要求 Tool 提交版本，其重复行为依赖状态机或调用审计。

代码证据：

- `backend/apps/events/models.py`：`CalendarEvent.version`；
- `backend/apps/events/services.py`：`UpdateEventCommand.expected_version`、事务行锁、
  `_ensure_version()` 与成功后的 `version += 1`；
- `backend/apps/tasks/models.py`：`Task.version`；
- `backend/apps/tasks/services.py`：`UpdateTaskCommand.expected_version` 与 `_ensure_version()`；
- `backend/apps/agents/tools/event_tools.py`、`task_tools.py`：Agent Tool Schema 要求提交版本。

## 3. 当前已有的幂等防线

### 3.1 AgentRun 入口

`AgentRun.operation_id` 全局唯一。同一入口逻辑操作不会创建两个不同 Run；Broker 入队失败时会释放
预留状态，允许客户端重试。这个边界防止重复提交整个 Agent 请求，但尚未作为所有下游写 Tool 的
稳定业务操作身份。

### 3.2 Tool Call 审计与结果回放

`ToolCallAudit` 对 `(run, tool_call_id)` 建立唯一约束。`ToolAuditMiddleware` 的行为是：

| 已有状态 | 行为 |
|---|---|
| 不存在 | 创建 `running`，记录 `tool.started` 并执行 |
| `completed` | 不执行副作用，返回保存的结果 |
| `running` | 拒绝重复接管 |
| `failed` | 不盲目重试，返回此前失败 |

它能保证**同一个技术 Tool Call**的回放，但不能识别恢复后新生成的 `tool_call_id` 是否仍代表旧业务
意图。Handoff Tool 和缺少可信 `AgentRun/tool_call_id` 的调用不进入该审计路径。

### 3.3 领域级幂等

当前较强的领域级实现包括：

- Reminder：`(user, deduplication_key)` 唯一；相同键同载荷返回原记录，相同键不同载荷报冲突；
- TaskExecutionSignal：`(user, idempotency_key)` 唯一，并验证任务、动作、时间、来源和 metadata；
- MemoryProposal：`(user, idempotency_key)` 唯一；重复 Tool Call 返回原 Proposal；
- TimeDecisionFeedback：用户级幂等键；
- ActionProposal：Proposal 身份与审批 `decision_idempotency_key`，并绑定精确 Tool 参数；
- ScheduleChangeBatch：独立唯一 `operation_id`；确定性自动重排由事实快照派生稳定操作 ID。

### 3.4 乐观锁、状态机与事务

- Event、Task、Reminder、SchedulePlan 更新使用版本检查；
- Event、Task 等写入在事务内取得用户级 PostgreSQL advisory transaction lock，并对目标行
  `SELECT FOR UPDATE`；
- 完成、取消等终态操作通常在目标已经处于相同状态时直接返回；
- 批量 Tool 通过 Application Service 事务执行，避免只写入半个批次；
- 写 Tool 不进入自动 Tool Retry，只有只读 Tool 对瞬时网络错误有限重试。

这些机制减少重复或并发覆盖，但只有返回同一业务结果、校验同键同载荷并由唯一约束兜底的路径，
才能称为完整领域幂等。

## 4. 当前写 Tool 风险矩阵

| Tool/类别 | 当前主要保护 | 不同 `tool_call_id` 重放风险 | 需要补强 |
|---|---|---|---|
| `mutate_events` 中 create | Audit、事务、冲突检查、HITL | 可能重复创建 | 稳定业务 operation ID 与批次成员键 |
| `mutate_events` 中 update/cancel/link | expected version、行锁、HITL | 旧版本通常冲突，但不重放首次结果 | 业务操作回执与结果重放 |
| `create_recurring_event` | Audit、整批事务、冲突预览、HITL | 可能重复创建整组 Series | Series operation ID + occurrence 派生键 |
| `create_task` / `create_task_batch` | Audit；批量事务/HITL | 可能重复创建 | Task/Batch operation ID |
| `update_task` / batch state | expected version、行锁、HITL | 旧版本冲突；新快照可再次更新 | 稳定操作记录和结果重放 |
| `change_task_state` / `cancel_task` | 状态机相同终态返回 | 多数同状态安全，轨迹语义仍需核对 | 操作 ID，避免重复审计/派生动作 |
| `complete_task` | 稳定 `request_id + task_id` 执行信号 | 同一 Run 内较强 | 统一到通用 operation identity |
| `reschedule_task` | Audit、用户写锁、事务 | 新 Call 可重复递增版本并重复审计 | expected version + operation ID |
| `create_reminder` | 领域唯一键与载荷冲突检查 | 当前 key 含 `tool_call_id`，新 Call 仍可能重复 | 使用稳定业务 operation ID 派生键 |
| Reminder update/target/cancel | version 或状态机、HITL | 冲突或相同终态；不重放原结果 | 操作回执；取消补稳定键 |
| Planning 写 Tool | expected version、事务、部分 operation ID、HITL | 依具体 Tool 而异 | 统一计划操作身份与回执 |
| `act_on_temporal_insight` | ownership、状态机/Service | 新 Call 可能重复产生处置副作用 | Insight action operation ID |
| Decision feedback | 用户级幂等键 | key 含 Tool Call 时新 Call 可重复 | 使用逻辑操作 ID |
| Memory write Tool | Proposal 唯一键、目标版本、Policy/HITL | 新 Call 可能生成新 Proposal；近重复检测不是严格保证 | 逻辑操作 ID + 同键异载荷冲突 |

历史上保留但未注册到当前 Time Steward 的单项 `create_event`、`update_event`、`cancel_event` Tool
不能被描述为当前主链路能力；主链路使用 `mutate_events`。补强时应优先覆盖实际注册 Tool。

## 5. 最关键的失败窗口

### 5.1 相同业务意图生成新 Tool Call ID

```text
call-A 创建成功
  -> Agent 在 checkpoint/响应边界恢复
  -> 模型生成参数相同的 call-B
  -> ToolAudit 认为是新调用
  -> Create 类 Tool 可能再次写入
```

这是当前最明确的缺口。

### 5.2 业务提交成功但 Audit 未完成

Application Service 的业务事务可能已经提交，而 Worker 在 `ToolCallAudit=completed` 之前退出。此时
Audit 可能保持 `running`。当前策略会拒绝同一个 Tool Call 再执行，避免盲目重复副作用，但 Run
不能仅凭 Audit 判断业务是否已经提交，也无法自动重放结果。

### 5.3 外部 Provider 的未知提交

未来外部日历写回或第三方通知可能已经被 Provider 接收，但本地尚未写回成功状态。仅靠 PostgreSQL
事务无法回滚远端副作用。必须要求 Provider 支持幂等键，或使用查询确认、补偿和人工处置状态；
当前外部日历主链路仍为只读，不能声称该问题已经解决。

## 6. 目标设计

### 6.1 稳定业务操作身份

新增持久化的业务操作回执，例如 `ToolOperation`，但应在实际实施时与现有 `ToolCallAudit`、
`ActionProposal` 统一建模，避免建立空抽象。最小字段应包括：

```text
user_id
agent_run_id
operation_id          # 不依赖 tool_call_id
operation_type
request_fingerprint   # 规范化后参数 hash，只用于同键异载荷检测
status                # claimed/completed/failed/unknown
result                 # 可重放的有界结果或资源引用
tool_call_id           # 本次技术调用，仅用于 trace
created_at/updated_at
```

唯一约束应基于：

```text
UNIQUE(user_id, operation_id, operation_type)
```

规则：

1. 同 operation ID、同 fingerprint：返回已有状态或结果；
2. 同 operation ID、不同 fingerprint：明确返回 idempotency conflict；
3. 不同 operation ID、相同参数：允许执行，保留用户有意重复操作；
4. `completed`：直接重放结果；
5. `claimed/running`：不得由第二个 Worker 并发接管，需 lease/超时恢复规则；
6. `unknown`：不自动重做外部副作用，进入 Provider 查询或人工恢复。

### 6.2 operation ID 如何跨恢复保持稳定

不能要求模型生成 operation ID。应由服务端在确定业务动作槽位时派生并注入，例如：

```text
AgentRun.operation_id
  + 受审批 ActionProposal.id（存在时）
  + workflow/node/intent slot
  + batch item index
  + operation schema version
```

同一 LangGraph checkpoint 恢复到同一动作槽位时得到相同 ID；用户明确发起新的请求会得到新的
`AgentRun.operation_id`。参数 fingerprint 只检查同一 operation ID 是否被错误复用于另一载荷，
不承担业务身份。

对于完全动态、无法稳定确定动作槽位的普通 ReAct 调用，第一版可优先使用已持久化的
`ActionProposal.id`（高风险路径）或在 Tool 首次执行前由 Runtime 建立 operation claim，并将该身份
写回 checkpoint state；不能把随机的新 `tool_call_id` 当作最终业务身份。

### 6.3 事务边界

本地 PostgreSQL 副作用应尽量在同一事务中完成：

```text
锁定/创建 ToolOperation claim
  -> 校验 fingerprint
  -> 执行 Application Service
  -> 保存 result/resource reference
  -> 标记 completed
  -> COMMIT
```

现有用户 advisory lock、实体行锁和 expected version 继续保留。operation ID 负责重复请求，版本负责
并发旧快照，两者不能互相替代。

外部副作用不能与本地数据库形成普通 ACID 事务，应采用 transactional outbox/dispatcher，并把稳定
operation ID 透传给支持幂等的 Provider。Provider 不支持时必须定义查询确认、补偿或 unknown 状态，
不能自动假定失败。

## 7. 建议实施顺序

### Phase I：补高风险本地 Create

1. 为 `mutate_events`、`create_recurring_event`、`create_task_batch` 定义稳定 operation ID；
2. 批次级 claim 与全部成员写入放在同一事务；
3. 批次成员 ID 由 batch operation ID + index 派生；
4. 同键异载荷返回明确冲突；
5. 完成结果保存资源 ID 列表，可在恢复后重放。

原因：这些路径副作用大、已进入 HITL，`ActionProposal.id` 可以提供稳定锚点，实施收益最高。

### Phase II：补普通本地写 Tool

覆盖 `create_task`、`reschedule_task`、Reminder、Decision feedback、Insight action 和 Memory Tool。
将当前由 `tool_call_id` 派生的领域键迁移为逻辑 operation ID；保留旧键兼容和审计字段。

### Phase III：统一恢复协议

1. 明确 `running` 的 lease、超时与接管规则；
2. 区分 retryable failure、terminal failure 和 unknown commit；
3. Worker 恢复时先查询 ToolOperation，再决定重放、等待、重试或人工介入；
4. 将 `request_id / AgentRun.operation_id / operation_id / tool_call_id` 统一写入低基数 Trace 关联字段。

### Phase IV：外部副作用

仅在实现外部日历写回等功能时增加 Outbox、Provider 幂等键、远端查询确认和补偿。当前阶段不得为
尚不存在的外部写回提前创建伪 Provider 或空恢复流程。

## 8. 测试与验收

每个写 Tool 至少增加以下固定测试：

1. 同 operation ID、相同参数、相同 tool call ID：返回首次结果；
2. 同 operation ID、相同参数、不同 tool call ID：仍返回首次结果；
3. 同 operation ID、不同参数：返回幂等冲突且不写业务数据；
4. 不同 operation ID、相同参数：允许形成两个有意的业务操作；
5. 两个 Worker 并发 claim：只允许一个执行；
6. 业务事务中途异常：业务事实和 operation receipt 一起回滚；
7. 提交后响应丢失：恢复可读取并重放结果；
8. 旧 `expected_version`：拒绝覆盖，但不得误报为首次业务操作已重放；
9. HITL 审批恢复生成新 tool call ID：不重复执行已批准动作；
10. 批量操作任一成员失败：整批回滚且可安全重试。

需要补做的真实验收：

- PostgreSQL 下两个 Celery Worker 并发执行同一 operation ID；
- Tool 成功提交后、Audit 完成前强制终止 Worker，再恢复同一 checkpoint；
- HITL 批准后在恢复边界重复投递 Celery task；
- 至少 100 次恢复/重投故障注入，统计重复业务事实数、冲突数和不可自动恢复数。

没有上述数据前，不应宣称全部写 Tool 达到 exactly-once。正确表述是：当前具备 AgentRun 入口防重、
同 Tool Call ID 的 Audit 回放、部分领域幂等和版本/事务保护；跨不同 Tool Call ID 的统一业务幂等
仍需按本文计划补齐。

