# ADR 0004：ActionProposal 与 LangGraph HITL 持久化边界

- 状态：已接受
- 日期：2026-07-19

## 背景

Phase 6 要求高风险操作在用户有效审批前绝不执行，同时审批必须可查询、可编辑、可拒绝、可过期，并支持并发控制、幂等恢复和执行审计。LangGraph checkpoint 能保存暂停的 Agent 执行状态，但不能替代 PostgreSQL 中可供业务 API 查询和治理的审批事实。

## 决策

1. Time Steward 使用 LangChain 官方 `HumanInTheLoopMiddleware` 在高风险 Tool 执行前触发 `interrupt()`；外层 Graph 不复制 Agent 内部 Tool Loop。
2. LangGraph PostgreSQL checkpointer 保存暂停点、消息和待执行 Tool Call；恢复时使用同一 `conversation_id/thread_id` 和 `Command(resume={"decisions": [...]})`。
3. Django `ActionProposal` 是审批业务事实的唯一权威来源，保存原请求、原始/编辑后参数、风险、有效期、版本、决定、执行结果、错误和幂等键。
4. 中断已经持久化后才创建 ActionProposal；任何 Tool 副作用都发生在有效批准或编辑批准恢复之后。
5. 审批 API 使用用户隔离、行锁、显式 `expected_version` 和决策幂等键。过期决定按拒绝语义安全恢复，不执行原 Tool。
6. Tool 仍通过 Application Service 修改业务事实。ToolAudit Middleware 同步更新 ActionProposal 的 `executing`、`executed` 或 `failed` 状态。
7. 高风险注册表只包含可真实执行且有测试覆盖的 Tool：`create_event` 允许 approve/edit/reject；`cancel_event`、`cancel_reminder`、`cancel_task` 只允许 approve/reject，避免审批时替换撤销目标。未来加入更新、物理删除、批量或外部操作时，仍须先实现对应 Service、Tool、风险策略和测试。
8. `Interrupt.value` 是待审批动作的运行时权威来源。ActionProposal 使用 `interrupt.id + action position` 建立临时 Tool Call 身份，不从父 Graph `messages` 推断嵌套 Agent 的待执行 Tool；恢复进入 ToolAudit Middleware 后再绑定真实 Tool Call ID。

## 备选方案

- 只使用 LangGraph interrupt payload：无法提供稳定审批列表、过期查询、并发版本和业务审计，不采用。
- 自定义审批节点替代官方 Middleware：会重复拆解 `create_agent()` 内部 Tool Loop，不采用。
- 审批后由 API 直接调用 EventService：会绕过被暂停的 Agent 轨迹和官方 edit/reject 语义，不采用。

## 原因

该边界同时保留 LangGraph 的可恢复执行能力和 PostgreSQL 的业务权威性，并让“是否审批”和“是否已经产生业务副作用”具有独立、可验证的证据。

## 影响

- AgentRun 新增 `waiting_approval` 状态。
- Celery Worker 负责初始运行和审批后的恢复；Beat 定期处理过期审批并以拒绝语义恢复。
- 部署 Phase 6 时必须同时迁移 Django 数据库并保留 LangGraph PostgreSQL checkpoint。
- 审批参数编辑仍由 Tool Schema 和 Application Service 在执行时做最终校验，前端不复制业务规则。
