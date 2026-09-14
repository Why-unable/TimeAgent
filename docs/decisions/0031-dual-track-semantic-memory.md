# ADR 0031：双路线长期记忆与受控语义写入

- 状态：已接受
- 日期：2026-08-31

## 背景

ADR 0015 已确定从日历、任务、提醒和执行信号确定性重建行为画像，但业务数据无法完整表达
“周五下午不要开会”等用户明确声明。直接让 LLM 修改长期记忆又会绕过用户隔离、Policy、版本、
审计和删除治理，并可能把临时对话或注入内容固化为未来排程约束。

## 决策

1. 行为记忆与语义记忆并行：前者从 PostgreSQL 业务事实确定性重建；后者只保存用户明确表达且
   通过 Policy 的类型化长期偏好。两者分区渲染，不互相覆盖业务事实。
2. PostgreSQL `SemanticMemory` 与 `MemoryProposal` 是语义记忆权威来源。LangGraph Store 只保存
   可重建投影，用于 Agent 召回，投影失败不得回滚权威写入。
3. 后台提取 LLM 只输出受限 `MemoryProposalPayload`，不得直接写 SemanticMemory。默认只处理本轮
   用户消息和有界相邻上下文，不保存系统提示、Tool 输出或模型私有推理。
4. Agent 使用标准 LangChain Tool Calling 接入 search/remember/update/forget，不新增自定义
   ToolNode。Tool 只能从可信 ToolRuntime 获取用户、AgentRun 和 Tool Call ID，并调用
   `SemanticMemoryToolService`，不得直接访问 ORM。
5. Search Tool 只返回当前用户 active、未过期的有界结果。Update/Delete 必须使用稳定 memory ID；
   写操作使用 Tool Call 派生幂等键并保存目标版本。
6. 默认写模式只生成 pending MemoryProposal，由记忆管理页审批。可选内联模式复用 ADR 0004 的
   ActionProposal/HITL；批准并恢复后才执行 Tool，并在再次验证目标快照和 Policy 后应用 Proposal。
7. Search、Write 和内联审批由独立开关控制；直接应用另使用 `confirm/shadow/enabled` 三态门禁。
   默认保持 confirm。未完成真实评测与部署验收前，生产环境不启用 enabled。

## 备选方案

- **只保留行为画像**：安全且可重建，但无法表达尚未反映到业务数据中的明确偏好，不采用。
- **LLM 直接 CRUD SemanticMemory 或 Store**：响应快，但缺少权威审批、并发版本和审计边界，不采用。
- **后台提取与 Tool 模式二选一**：会遗漏隐式偏好或即时“记住/忘记”意图；本项目让两条入口共享
  Proposal、Policy 和持久化出口。
- **首版引入向量数据库**：当前有界类型化 Collection 尚无召回不足的 Benchmark 证据，暂不采用。

## 影响与限制

- 语义记忆写入增加 MemoryProposal 审批、版本冲突和 Store 投影任务，但不会改变业务数据库事实。
- 内联审批不会进行二次页面确认；ActionProposal 证明用户决定，MemoryProposal 保留记忆领域审计。
- 当前精确/子串 Search 不等于语义向量检索；效果、延迟、Token 和用户接受率均需要补测。
- 自动化测试已经覆盖权限隔离、幂等、版本冲突和内联恢复主链路；真实 PostgreSQL Checkpoint、
  Celery Worker 重启和移动端审批仍需部署验收。
- ADR 0032 在本边界之上定义显式低风险指令的分级授权与可撤销直接应用；它不改变后台推断和
  高影响约束必须确认的原则。
