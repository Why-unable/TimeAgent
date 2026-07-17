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
```

这些端点要求认证，写操作必须经过对应 Application Service。提醒 DELETE 表示取消，
不会物理删除记录；创建请求的时间必须包含明确 UTC 偏移，并携带用户范围内的幂等键。

事件和任务的时间输入同样必须包含明确 UTC offset。事件 PATCH 与 DELETE 通过必填查询参数
`expected_version` 执行乐观锁校验，过期版本返回 `409`；事件 DELETE 表示取消。任务状态不
接受普通 PATCH，完成任务必须调用 `/complete/`，从而保证状态机时间戳一致。

Today 端点按当前用户 IANA 时区汇总今日日程、今日计划任务、今日截止任务、历史逾期任务、
待处理提醒、时间冲突和下一日程。任务分桶与冲突均由后端确定，前端不重复实现业务规则。
