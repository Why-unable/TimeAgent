# ADR 0007：使用短生命周期 Briefing Agent 执行只读调研

- 状态：Accepted
- 日期：2026-07-20

## 背景

原 Briefing Workflow 固定并行执行 Calendar、Task、Weather、News Section，再将结果交给
无 Tool 的 Briefing Editor。该设计适合单日固定简报，但不能根据“未来一周”等请求改变
时间范围，也无法在天气或新闻失败后调整查询。新闻主题未被 Feed 标签覆盖时也缺少搜索
回退能力。

## 决策

1. 使用 LangChain `create_agent()` 建立独立 Briefing Agent。
2. Briefing Agent 只获得日程、任务、天气、新闻和可信新闻目录 Tool，不获得业务写入 Tool。
3. Time Steward 通过 `transfer_to_briefing` 传递结构化日期范围、板块、地点、主题、约束和
   上次简报反馈；不传递完整聊天历史。
4. 定时触发直接构造相同的 BriefingRequest，不先调用 Time Steward。
5. Briefing AgentState 不配置 checkpointer；工具证据、来源、失败和最终报告复制到
   PostgreSQL `BriefingRun`，数据库仍是审计事实来源。
6. 天气/新闻外部 Tool 使用 `ToolRetryMiddleware` 做有限指数退避；耗尽后用
   `ToolErrorMiddleware` 将错误交回 Agent，使其披露缺口并继续生成。
7. Agent 返回 `BriefingAgentReport`，包含最终 Draft、调研摘要、失败项、未满足要求和覆盖
   范围。后端确定性校验 Tool 尝试、日期覆盖和来源 ID；失败时最多追加一次修复请求，之后
   使用确定性降级，禁止无限自循环。
8. 手动 Handoff 保留发起调用的 AIMessage/ToolMessage 配对，最终简报另写 AIMessage；自动
   触发没有 Tool call，因此不伪造 ToolMessage。
9. Skill 采用 LangChain 的渐进披露概念，但在出现第一个真实专业简报 Skill 前不创建空
   Registry 或伪实现。
10. Briefing Agent 直接将 `BriefingAgentReport` Schema 传给 `create_agent()`，由 LangChain
    根据模型 profile 自动选择 `ProviderStrategy` 或 `ToolStrategy`。DeepSeek 通过模型配置
    `enable_thinking: false` 映射到官方协议 `thinking.type=disabled`，不再使用 prompted JSON
    作为主路径。对于声明支持原生结构化输出、但实际无法承载完整简报 Grammar 的中转站，
    使用 `structured_output_strategy: tool` 显式选择官方 `ToolStrategy`。默认 `auto` 仍直接
    传递 Schema，由 LangChain 自动选择。确定性业务校验与有限修复仍作为 Schema 校验之外的安全边界。

## 原因

官方 LangChain 将 `create_agent` 用于模型、Tool 和 Middleware 组成的 Agent 循环；将
LangGraph 用于需要确定性控制的外层编排。Handoff 只传递必要上下文可以避免下游 Agent 被
主会话历史污染。Tool retry 适合瞬时外部 API 故障，而确定性校验比仅靠提示词更适合保证
来源和覆盖范围。

参考：

- https://docs.langchain.com/oss/python/langchain/agents
- https://docs.langchain.com/oss/python/langchain/middleware/built-in
- https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs
- https://docs.langchain.com/oss/python/langchain/multi-agent/skills

## 后果

- 简报可以按请求决定调研步骤和日期范围，并对外部失败做有限恢复。
- 每次简报会增加若干模型调用，必须受模型/Tool 调用上限约束。
- Briefing Agent 内部消息不长期保存；需要通过 BriefingRun 调研报告而不是内部对话复盘。
- 新闻仍只访问运维维护的可信 Feed，不开放任意网页搜索。
