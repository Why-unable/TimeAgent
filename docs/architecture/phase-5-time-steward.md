# Phase 5：Time Steward Agent

Phase 5 使用 LangChain v1 `create_agent()` 建立一个受限的主 Agent。Outer Graph 仍只负责
触发路由、持久化边界和未来 Handoff；模型—工具循环完全由 `create_agent()` 提供。

## 运行链路

```text
Chat REST API
  → Conversation / AgentRun
  → Celery execute_agent_run task
  → TriggerEnvelope + trusted RuntimeContext(actor)
  → Outer Graph(user_message)
  → Time Steward create_agent loop
  → ToolRuntime → Application Service → Django ORM → PostgreSQL
  → AgentEvent → resumable SSE → Chat UI
```

`actor` 是入口认证得到的 Django User，只存在于单次 Runtime Context。模型不能提交
`user_id`，Tool 也不能从参数选择用户。Agent State 只保存 messages；Outer Graph 的
`RemainingSteps` 等 managed channel 不进入 `create_agent()` 的输入/输出 Schema。

## Tool 与风险边界

只读 Tool 提供当前时间、偏好、事件、任务、提醒、冲突与空闲时段。Phase 5 允许的低风险
写 Tool 为创建事件、创建任务、完成/重排任务和幂等创建提醒。取消、删除、批量重排、外部
通信和跨用户操作不注册，留给 Phase 6 ActionProposal/HITL。

Tool 仅负责参数适配、Runtime actor 注入和结果序列化；领域规则、权限范围、事务与状态机
都在 Application Service。ToolCallAudit 以 `(run, tool_call_id)` 唯一约束提供调用级回放，
Reminder 另有用户范围的领域幂等键。

## Middleware

- 动态 Prompt 注入可信当前时间、IANA 时区、locale 和运行模式；
- Tool Policy 在每次模型调用前按 `read_only` 裁剪预注册 Tool；
- Model/Tool Call Limit 防止失控循环；
- Model Retry 与只读 Tool Retry 处理暂时故障，非幂等写 Tool 不自动重试；
- Model Fallback 在主模型重试耗尽后按配置切换备用 Provider；
- Tool Error 只把可由模型修正的领域/参数错误转换为 ToolMessage；
- Summarization 在长对话接近阈值时压缩 checkpoint messages；
- Tool Audit 记录 started/completed/failed，不向前端暴露 Tool 参数。

模型、Graph 限制和上述 Middleware 参数统一由 `backend/config/agent.example.yaml` 加载；密钥
仍由环境变量注入。配置边界见 `docs/architecture/agent-configuration.md`。

## 运行与流事件

Conversation ID 同时作为 LangGraph `thread_id`。AgentRun 保存一次用户消息的状态、最终回复
和安全错误；AgentEvent 以 run 内递增 sequence 保存前端协议。SSE 可通过游标重放，Nginx
禁用该响应的代理缓冲。

前端使用 `/chat/:conversationId` 作为会话稳定地址，并在聊天区提供按最近活跃时间排序的
历史列表。进入旧地址时，从 PostgreSQL 中的 Conversation/AgentRun 回载完整对话；如果最后
一个 Run 仍在执行，则从持久化事件流继续接收回复。`/chat` 表示尚未持久化的新聊天，只有
发送第一条消息时才创建 Conversation 并跳转到稳定地址。这个交互参考 ChatGPT 的历史侧栏、
重新打开后继续对话和显式新建聊天模式；业务事实仍以本项目 PostgreSQL 为唯一来源。

`POST /api/v1/chat/messages/` 只持久化 AgentRun、预留唯一 Celery task ID 并返回 `202`；
Worker 在请求生命周期外执行 Outer Graph。相同 `operation_id` 只会入队一次，task ID 同时
允许 Worker 丢失后的同任务重投继续使用 LangGraph checkpoint 和 Tool 审计幂等边界。Broker
入队失败会释放预留，允许客户端安全重试。

SSE 在 Run 处于 pending/running 时持续读取 PostgreSQL 中的新 AgentEvent，定期发送 heartbeat，
并在 completed/failed/cancelled 终态后关闭。客户端保存最后事件 ID；非终态断线时使用
`Last-Event-ID` 自动重连，因此增量消息和 Tool 生命周期既实时可见，也可从持久化事件恢复。
取消首先持久化 `run.cancelled`，Worker 在 LangGraph 流事件边界协作停止。

## 固定评测

`backend/tests/fixtures/time_steward_eval.json` 保存必须调用和禁止调用的 Tool 轨迹。快速测试使用
脚本模型验证 Agent、Middleware 和 Tool 边界；发布前使用真实配置模型运行：

```bash
cd backend
uv run python manage.py evaluate_time_steward
```

可通过 `--model deepseek` 选择模型，或重复传入 `--case <id>` 只运行指定用例。评测使用固定
当前时间和测试用户，真实调用 Application Service，但在数据库事务末尾统一回滚，不污染业务数据。

## 官方文档依据

- [Agents](https://docs.langchain.com/oss/python/langchain/agents)
- [Tools / ToolRuntime](https://docs.langchain.com/oss/python/langchain/tools)
- [Middleware](https://docs.langchain.com/oss/python/langchain/middleware)
- [Streaming](https://docs.langchain.com/oss/python/langchain/streaming)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
