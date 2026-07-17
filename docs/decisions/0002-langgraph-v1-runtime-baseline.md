# ADR 0002：LangGraph v1 运行时基线

- 状态：已接受
- 日期：2026-07-17

## 背景

Phase 4 需要建立外层 LangGraph、短期 checkpoint、长期 store、运行时上下文和后续中断恢复
能力。项目规范同时要求 Time Steward Agent 在 Phase 5 使用 LangChain `create_agent()` 和
middleware，不能自行重建 Agent loop。

本决策依据 LangChain 官方 Python 文档的当前 v1 API：

- [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Add memory](https://docs.langchain.com/oss/python/langgraph/add-memory)
- [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [Agents and middleware](https://docs.langchain.com/oss/python/langchain/agents)
- [Context overview](https://docs.langchain.com/oss/python/concepts/context)
- [Tools](https://docs.langchain.com/oss/python/langchain/tools)
- [Custom middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom)

## 决策

1. 外层确定性编排使用 LangGraph v1 `StateGraph`，不手写状态机执行引擎。
2. 单次调用依赖通过 `context_schema` 和 `Runtime[RuntimeContext]` 注入；不把数据库连接、
   当前时间或只读策略持久化进 `AppState`。
3. 短期状态使用 `PostgresSaver`，长期软性记忆使用 `PostgresStore`。两者来自
   `langgraph-checkpoint-postgres`，首次部署必须显式执行各自的 `setup()`。
4. 对话 checkpoint 以 `conversation_id` 作为 `thread_id`；Reminder Dispatcher 保持
   确定性 Celery 流程，不依赖 Agent checkpoint。
5. 恢复使用 LangGraph 原生 `Command(resume=...)` 和 `interrupt()`；节点必须满足可重放和
   幂等要求，不在中断前执行不可重复副作用。
6. Graph 调用限制使用 LangGraph 原生 `recursion_limit`/运行时 step 信息；模型和工具调用
   限制留给 Phase 5 的 `ModelCallLimitMiddleware`、`ToolCallLimitMiddleware` 等官方
   middleware。
7. 依赖由 `uv` 管理。`pyproject.toml` 保持兼容主版本范围，`uv.lock` 固定本次验证的完整
   依赖图。
8. PostgreSQL 资源使用官方同步/异步上下文管理器控制连接生命周期；首次部署通过幂等的
   `python manage.py setup_langgraph` 显式执行 Saver 与 Store 的官方迁移。
9. Trigger Router 使用带完整目标类型标注的 LangGraph `Command(update=..., goto=...)`，
   在同一步记录 `active_workflow` 并完成确定性路由，不叠加静态分支边。
10. Outer Graph 同时编译持久化和无状态拓扑。`reminder_due` 固定选择无 Checkpointer、无
    Store 的拓扑并调用现有 `ReminderDispatcher`；其他触发选择 PostgreSQL 持久化拓扑。
11. 仅最外层 Graph 编译 Checkpointer；未来 Agent 和子图继承父图持久化。恢复必须使用
    相同 `thread_id` 和唯一允许作为 invoke 输入的 `Command(resume=...)`，节点中断前的逻辑
    必须可重放且不得包含非幂等副作用。
12. 每次调用在 `RunnableConfig` 顶层设置 `recursion_limit` 与 `max_concurrency`。AppState
    暴露官方 `RemainingSteps` managed value 供工作流主动安全退出；未主动收敛时，将
    `GraphRecursionError` 映射为稳定的 `GraphStepLimitExceededError`。
13. `TriggerEnvelope.operation_id` 标识可重放、可幂等的逻辑操作并进入 checkpoint；
    `RuntimeContext.request_id` 只标识当前 HTTP/Celery/invoke 调用，可在恢复时变化。
14. `conversation_id` 不写入 `AppState`。LangGraph checkpoint 地址只使用
    `RunnableConfig.configurable.thread_id`；业务节点确有需要时，通过只读 Runtime Context
    获取领域会话标识。
15. `RunnableConfig.metadata` 携带 `operation_id`、`request_id`、`user_id` 和触发类型用于
    追踪；`configurable` 只保留 LangGraph 持久化所需的 `thread_id`，不作为任意业务数据袋。
16. `pending_interrupts()`、`resume()`、Saver/Store 生命周期和执行限制属于 Graph 控制面，
    保持在节点外，由后续应用服务调用，不创建自省或恢复节点。

## 状态边界

`AppState` 继承官方 `AgentState`，直接复用带 `add_messages` reducer 的 `messages`。项目只
扩展当前 Outer Graph 确实需要持久化的字段：`trigger_type`、`trigger_payload`、
`operation_id`、`active_workflow`、`workflow_result` 与 `remaining_steps`。

- Agent 的工具调用保存在 `AIMessage.tool_calls`；工具结果使用 `ToolMessage`；最终回复是
  最后一条 `AIMessage`，不再平行维护 `tool_results` 或 `final_response`。
- `briefing_definition_id` 保留在 trigger payload，未来由 Briefing 工作流定义专属状态；
  `pending_action_id` 等 HITL 字段由 Phase 6 的业务状态或 middleware 按需声明。
- Runtime Context 保存用户、时区、语言、权限、当前时间和本次请求标识等单次运行只读依赖。
- Store 用于跨线程长期软性记忆；PostgreSQL 领域表继续是任务、日程和提醒的权威数据源。
- Middleware 需要额外计数器或控制字段时，优先通过自身 `state_schema` 声明，避免继续扩大
  全局 `AppState`。

T030 锁定的直接依赖为 LangChain 1.x、LangGraph 1.x、PostgreSQL checkpoint 3.x、
Pydantic 2.x 与 `psycopg[binary,pool]`。锁文件当前解析到 LangChain 1.3.14、LangGraph
1.2.9、`langgraph-checkpoint-postgres` 3.1.0 和 Pydantic 2.13.4。

## Middleware 基线

锁定版本已验证以下官方公开 API 可导入，供 Phase 5 按实际风险组合，而不是在 Phase 4
创建空壳 middleware：

- `SummarizationMiddleware`
- `TodoListMiddleware`
- `HumanInTheLoopMiddleware`
- `ModelCallLimitMiddleware` / `ToolCallLimitMiddleware`
- `ModelRetryMiddleware` / `ToolRetryMiddleware`
- `ModelFallbackMiddleware`

自定义 Runtime Context、动态工具策略、审计和 Memory Policy 只在存在真实 Agent、工具和
持久化行为后实现。

## 后果

- Phase 4 可以直接围绕官方持久化、路由和恢复语义开发；
- Phase 5 可以复用 `create_agent()` 与内置 middleware，不重复实现成熟功能；
- PostgreSQL 会增加 LangGraph 管理的 checkpoint/store 表，部署流程需要独立 setup 步骤；
- 主版本升级必须重新核对公开 API、迁移持久化数据并更新本 ADR。
