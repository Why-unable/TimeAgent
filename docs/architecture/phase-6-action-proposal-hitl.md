# Phase 6：ActionProposal 与 HITL

> 当前状态说明（2026-09-16）：Phase 6 已完成。本文保留最初验收设计；当前 Event 模型可见
> 写入口已经收敛为 `mutate_events` 与 `create_recurring_event`。风险策略中仍存在未注册的
> `create_event`、`create_event_batch`、`update_event`、`cancel_event` 旧名称，已列入 Phase 11
> 的 Tool Manifest/策略一致性治理，不能再把这些旧名称描述为当前模型可见入口。

## 目标

Phase 6 为高风险 Agent 写操作建立“提出 → 展示 → 决定 → 恢复 → 执行 → 审计”闭环。未经有效审批的操作不会进入 Tool Handler，因此不能修改 CalendarEvent 等业务事实。

嵌套 Agent 的 interrupt 会传播到 Outer Graph。审批动作只从官方 `Interrupt.value` 中的 `action_requests` 与 `review_configs` 读取，并以 `Interrupt.id + action position` 建立稳定临时身份；父 Graph 的 `messages` 不作为子 Graph 待执行 Tool Call 的校验来源。

## 当前风险策略

| Tool | 风险 | 决策 | 行为 |
| --- | --- | --- | --- |
| `mutate_events` | high | approve / edit / reject | 原子创建、修改、取消或关联日程，审批后执行 |
| `create_recurring_event` | high | approve / edit / reject | 有限重复日程在审批后创建 |
| `create_task_batch` | high | approve / edit / reject | 批量任务在审批后原子创建 |
| `apply_schedule_plan` / `apply_local_replan` | high | approve / reject | 批量应用计划或受控局部重排 |
| `cancel_reminder` | high | approve / reject | 审批后取消尚可撤销的提醒 |
| `cancel_task` | high | approve / reject | 审批后将活动任务转换为 cancelled，不物理删除 |
| `remember/update/forget_time_preference` | high | approve / reject | 长期偏好变更在审批后生效 |
| 查询 Tool | read | 无审批 | 直接执行 |
| 其他低风险写入 Tool | low | 无审批 | 经 Service 执行后审计并告知用户 |

撤销 Tool 必须先通过查询唯一确定当前用户拥有的目标。撤销审批不允许 edit，避免审批时把目标 ID 改成另一个对象。物理删除和外部写入仍未开放；日程修改和部分批量操作已通过组合 Tool、版本保护、事务与 HITL 开放。

## 执行序列

```text
模型产生当前注册的高风险 Tool Call
  → HumanInTheLoopMiddleware.after_model
  → LangGraph interrupt + PostgreSQL checkpoint
  → ActionProposal(awaiting_approval) + approval.required SSE
  → AgentRun(waiting_approval)
  → 用户 approve / edit / reject
  → 审批 API 行锁、版本与幂等校验
  → Celery 使用同一 conversation_id/thread_id 恢复
  → Command(resume={decisions: [...]})
  → approve/edit: Tool → 对应 Application Service → ORM
  → reject/expired: 生成拒绝 ToolMessage，不执行 Tool
  → ToolCallAudit + ActionProposal 执行结果
  → Agent 继续生成最终回答
```

## 状态

ActionProposal：

```text
awaiting_approval
  ├─ approve/edit → approved → executing → executed
  │                                  └────→ failed
  ├─ reject       → rejected
  └─ timeout      → expired
```

`approved` 只代表用户已决定，不代表业务写入成功；只有 `executed` 且包含执行结果才表示 Tool 已完成。`failed` 保留脱敏错误，业务 Service 的事务保证失败写入不被提交。

## API

```text
GET  /api/v1/action-proposals/
GET  /api/v1/action-proposals/{id}/
POST /api/v1/action-proposals/{id}/approve/
POST /api/v1/action-proposals/{id}/edit/
POST /api/v1/action-proposals/{id}/reject/
```

决定请求必须携带 `expected_version` 和客户端生成的 `operation_id`。编辑决定还需提交完整的 `action_payload`。后端始终重新校验用户、状态、版本、有效期和允许的决定类型。

## 前端

- `/approvals` 集中展示等待审批、批准、拒绝、执行、过期和失败状态；
- Chat 收到 `approval.required` 后读取结构化 Proposal 并显示同一审批卡片；
- 卡片显示原请求、风险解释、对象、时间、影响范围、冲突和完整参数；
- 前端按 AgentRun 保存最后一个 SSE cursor，批准恢复后从 `approval.required` 之后继续订阅，不重放旧消息；
- `waiting_approval` 仅在没有 Celery resume reservation 时结束 SSE；审批 API 已保留恢复任务时，连接会等待 Worker 将 Run 切回 `running`，避免批准与 Worker 接管之间的竞态；
- 前端编辑 JSON 只改善交互，Tool Schema 和 Application Service 是最终校验边界。

## 过期

默认有效期由 `ACTION_PROPOSAL_TTL_SECONDS` 控制（默认 86400 秒）。Celery Beat 每 60 秒将到期 Proposal 标记为 `expired`，并用官方 reject 决策恢复暂停运行；原高风险 Tool 不执行。

## 验证重点

- 使用真实 HumanInTheLoopMiddleware 和 checkpointer 证明审批前无 CalendarEvent 写入；
- 证明 cancel_event、cancel_reminder、cancel_task 在审批前不改变状态，批准后只进行可审计的状态转换；
- approve、edit、reject、expired 均覆盖恢复轨迹；
- API 覆盖用户隔离、乐观版本、行锁语义和决策幂等；
- Tool 执行失败记录为 failed，不伪装为 executed；
- OpenAPI、前端类型、组件测试和 Playwright 覆盖审批入口。
