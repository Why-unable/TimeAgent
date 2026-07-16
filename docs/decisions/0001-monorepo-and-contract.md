# 0001：Monorepo 结构与 OpenAPI 契约生成

## 状态

已接受

## 背景

仓库起初仅包含后端与前端规范，没有工程代码。开发指南要求建立 Django、React、Compose 和统一契约生成机制，同时避免提前创建完整业务模块。

## 决策

采用根目录 Monorepo：`backend/`、`frontend/`、`infra/`、`docs/`。后端使用 `uv` 管理 Python 依赖；前端使用 npm。Django 通过 drf-spectacular 生成 `backend/openapi.json`，前端使用 openapi-typescript 生成 `src/api/generated/schema.d.ts`。

Compose 中保留独立 `frontend` 静态站点容器，由入口 `nginx` 代理前端和 Django。该拓扑明确包含规范要求的全部服务，并允许后续将前端构建产物整合到入口 Nginx。

## 备选方案

- 前后端拆分为两个仓库；
- 手写 TypeScript API 类型；
- 开发阶段只使用 Vite dev server，不创建前端容器；
- 将前端构建直接嵌入唯一 Nginx 镜像。

## 原因

Monorepo 更适合原子更新 OpenAPI 契约；自动生成类型可减少前后端漂移；独立前端容器使 Phase 0 的 Compose 服务清单和职责清晰。

## 影响

- API 变更必须依次执行 `make api-schema` 与 `make frontend-api`；
- Docker 构建需要同时访问 Python、npm 和基础镜像仓库；
- 当前 Compose 偏向可验证的基础部署，生产环境仍需补充 TLS、静态文件持久化和更严格的安全配置。

