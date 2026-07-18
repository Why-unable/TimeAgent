# ADR 0003：Time Steward 运行时与可信身份边界

- 状态：已接受
- 日期：2026-07-17

## 背景

Phase 5 将使用 LangChain v1 `create_agent()` 实现 Time Steward。Agent Tool 必须访问当前
认证用户的领域数据，但不能直接查询 Django ORM，也不能相信模型提供的用户标识。项目当前
使用 Django 默认 User 整数主键，因此 Trigger Envelope 不能继续强制 UUID 用户标识。

本决策依据以下 LangChain 官方文档：

- [Agents](https://docs.langchain.com/oss/python/langchain/agents)
- [Runtime](https://docs.langchain.com/oss/python/langchain/runtime)
- [Context overview](https://docs.langchain.com/oss/python/concepts/context)
- [Tools](https://docs.langchain.com/oss/python/langchain/tools)
- [Middleware](https://docs.langchain.com/oss/python/langchain/middleware)
- [Streaming](https://docs.langchain.com/oss/python/langchain/streaming)

## 决策

1. `TriggerEnvelope.user_id` 使用规范化的非空字符串，兼容当前整数主键和未来 UUID 主键；
   值只能由可信 HTTP/Celery 入口生成，不能来自模型 Tool 参数。
2. 已认证的 Django `User` 作为 `RuntimeContext.actor` 注入。Context 是单次运行的只读依赖，
   不进入 `AppState`、checkpoint、Store 或模型消息。
3. Runtime Context 同时校验 `actor.pk` 与 `user_id` 一致。Phase 5 Tool 只从
   `ToolRuntime[RuntimeContext]` 获取 actor，并调用 Application Service；Tool 内禁止 ORM。
4. `RunnableConfig.configurable.thread_id` 继续只负责 checkpoint 地址；请求追踪信息放入
   metadata；用户身份和权限不从 configurable 读取。
5. Time Steward 使用一个 `create_agent()` 循环并作为 Outer Graph 子图注入，不把模型—工具
   循环复制为外层节点。只有 Trigger Router、Handoff 和确定性工作流保留在 Outer Graph。
6. Phase 5 优先使用官方 Middleware：调用限制、模型重试、模型回退、工具策略和摘要。
   HITL 与 ActionProposal 仍属于 Phase 6，不在本阶段提前实现。
7. Agent 工具调用、`ToolMessage` 和最终 `AIMessage` 只通过继承自 `AgentState` 的 messages
   reducer 流转；领域事实仍以 Django PostgreSQL Models 为权威来源。
8. 流事件从 LangChain/LangGraph 的 `messages`、`updates` 和 `custom` stream mode 适配为
   项目统一事件协议；不得向前端暴露私有推理、隐藏 Prompt 或敏感 Tool 参数。

## Phase 5 交付顺序

1. 可信 Actor Runtime Context；
2. 只读 Tool；
3. 低风险写 Tool 与风险策略；
4. `create_agent()` 与 Outer Graph；
5. 官方 Middleware；
6. Conversation、AgentRun 与审计；
7. Chat API、流事件和 SSE 恢复；
8. 最小 Chat UI 与固定评测集。

## 后果

- Tool 不需要也不允许根据模型参数重新选择用户；
- Runtime Context 包含 Django 对象，因此它只能作为进程内调用依赖，不能序列化为持久化状态；
- 未提供可信 actor 的运行仍可执行不访问用户数据的 Phase 4 确定性流程，但 Phase 5 业务 Tool
  必须明确拒绝缺少 actor 的调用；
- 如果未来切换自定义 UUID User 模型，Envelope、Context 和 Tool 接口无需再次改变。
