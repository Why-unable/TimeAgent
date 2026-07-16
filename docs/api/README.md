# API 契约

运行 `make api-schema` 生成 `backend/openapi.json`，运行 `make frontend-api` 进一步生成前端 TypeScript 类型。生成文件来自后端 Schema，不应手工编辑。

当前业务端点：

```text
GET   /api/v1/preferences/me/
PATCH /api/v1/preferences/me/
```

该端点要求认证，更新操作必须经过 `UserPreferenceService`。
