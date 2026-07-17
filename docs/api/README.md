# API 契约

运行 `make api-schema` 生成 `backend/openapi.json`，运行 `make frontend-api` 进一步生成前端 TypeScript 类型。生成文件来自后端 Schema，不应手工编辑。

当前业务端点：

```text
GET   /api/v1/preferences/me/
PATCH /api/v1/preferences/me/
GET   /api/v1/reminders/
POST  /api/v1/reminders/
DELETE /api/v1/reminders/{id}/
```

这些端点要求认证，写操作必须经过对应 Application Service。提醒 DELETE 表示取消，
不会物理删除记录；创建请求的时间必须包含明确 UTC 偏移，并携带用户范围内的幂等键。
