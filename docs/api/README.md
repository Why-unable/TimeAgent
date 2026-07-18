# API 契约

运行 `make api-schema` 生成 `backend/openapi.json`，运行 `make frontend-api` 进一步生成前端 TypeScript 类型。生成文件来自后端 Schema，不应手工编辑。

当前业务端点：

```text
GET   /api/v1/preferences/me/
PATCH /api/v1/preferences/me/
GET   /api/v1/reminders/
POST  /api/v1/reminders/
DELETE /api/v1/reminders/{id}/
GET   /api/v1/events/
POST  /api/v1/events/
GET   /api/v1/events/{id}/
PATCH /api/v1/events/{id}/
DELETE /api/v1/events/{id}/
GET   /api/v1/tasks/
POST  /api/v1/tasks/
GET   /api/v1/tasks/{id}/
PATCH /api/v1/tasks/{id}/
POST  /api/v1/tasks/{id}/complete/
GET   /api/v1/today/
GET   /api/v1/chat/conversations/
POST  /api/v1/chat/conversations/
GET   /api/v1/chat/conversations/{id}/
POST  /api/v1/chat/messages/
GET   /api/v1/chat/runs/{id}/
POST  /api/v1/chat/runs/{id}/cancel/
GET   /api/v1/chat/runs/{id}/events/
```

这些端点要求认证，写操作必须经过对应 Application Service。提醒 DELETE 表示取消，
不会物理删除记录；创建请求的时间必须包含明确 UTC 偏移，并携带用户范围内的幂等键。

事件和任务的时间输入同样必须包含明确 UTC offset。事件 PATCH 与 DELETE 通过必填查询参数
`expected_version` 执行乐观锁校验，过期版本返回 `409`；事件 DELETE 表示取消。任务状态不
接受普通 PATCH，完成任务必须调用 `/complete/`，从而保证状态机时间戳一致。

Today 端点按当前用户 IANA 时区汇总今日日程、今日计划任务、今日截止任务、历史逾期任务、
待处理提醒、时间冲突和下一日程。任务分桶与冲突均由后端确定，前端不重复实现业务规则。

Chat 端点要求认证。`POST /messages/` 接收 `conversation_id`、`message` 和可选的客户端
`operation_id`，以 `202 Accepted` 返回已排队的持久化 AgentRun；相同 operation ID 不能
关联不同输入且只会排队一次。Celery Worker 在请求生命周期外执行 Agent。事件端点使用
`text/event-stream`，事件包含单调递增 `id`，客户端可通过 `Last-Event-ID` 或 `cursor`
恢复，并保持连接直到 Run 进入终态。Phase 5 事件类型包括 `agent.started`、`tool.started`、`tool.completed`、
`tool.failed`、`message.delta`、`message.completed`、`run.failed` 和 `run.cancelled`。

`GET /conversations/{id}/` 返回当前用户的一段会话及按创建时间排序的 AgentRun。前端据此把
每个 Run 的 `input_message` 与 `final_response` 重建为历史消息；pending/running Run 会重新
连接其 SSE 流。会话详情和列表都执行用户隔离，其他用户的 ID 返回 `404`。
