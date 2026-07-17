# Time Agent

Time Agent 是以时间为核心的个人智能事务管理系统。本仓库当前已完成 **Phase 4**，具备提醒闭环、结构化日程与任务管理、每日工作台，以及可持久化、可路由、可恢复的 LangGraph 运行时基础设施。

> 当前已完成工程骨架、用户时间偏好、统一时区工具、提醒闭环、日程、任务、Today 汇总和 Outer Graph；Time Steward Agent 与简报业务将在后续阶段实现。

## 当前能力

- Django 5.2、DRF、PostgreSQL、Redis 与 Celery 基础配置；
- development、test、production 三套 Django settings；
- `/health/live`、`/health/ready`、`/api/schema/`；
- React、TypeScript、Vite、Router、TanStack Query、Zustand 与 Tailwind；
- 响应式基础 Layout、系统状态页、全局错误边界和统一 API Client；
- Docker Compose 与 Nginx 入口代理；
- drf-spectacular → openapi-typescript 契约生成；
- pytest、Ruff、mypy、Vitest、RTL 和 Playwright 基础配置；
- UserPreference 模型、迁移、Application Service 和认证 API；
- IANA 时区校验、UTC 转换以及 DST 歧义/不存在时间检测；
- 时间偏好页面、统一前端时间工具和用户时区展示；
- Reminder 模型、幂等约束、调度索引和确定性状态机；
- ReminderService、创建命令以及并发安全的幂等创建；
- 基于 Celery Beat 的到期扫描、幂等发送、失败重试和 Console Provider；
- 认证隔离的提醒 REST API，以及提醒列表、创建、取消和状态展示页面。
- CalendarEvent 模型、UTC/IANA 时间校验、外部身份约束、版本号和时间查询索引。
- Task 模型、父子层级、截止/计划时间区分、标签校验和确定性状态机。
- EventService 与 TaskService，包含用户隔离、事务锁、事件乐观锁、任务完成和重排。
- 半开区间日程冲突检测，以及结合用户工作时段、事件和计划任务的空闲候选搜索。
- 认证隔离的 CalendarEvent/Task REST API、事件版本冲突响应与任务完成端点。
- FullCalendar 月/周/日界面、日程创建/编辑/取消，以及任务分类、分组、编辑和完成界面。
- 按用户 IANA 时区生成的 Today 汇总 API 与每日工作台，包含时间线、任务分桶、提醒、冲突和下一日程。

## 技术栈

后端使用 Python 3.12、Django、Django REST Framework、PostgreSQL、Redis、Celery、LangChain v1、LangGraph v1 与 `uv`。前端使用 React、TypeScript、Vite、React Router、TanStack Query、Zustand、Tailwind、FullCalendar、Vitest 和 Playwright。部署基础为 Docker Compose 与 Nginx。

## 目录

```text
.
├── backend/             Django、Celery、测试与 uv 配置
├── frontend/            React SPA、测试与 API 类型
├── infra/nginx/         入口 Nginx 配置
├── docs/                架构、API 与 ADR
├── docker-compose.yml
├── Makefile
├── AGENTS.md
└── ROADMAP.md
```

## 环境要求

- Python 3.12；
- `uv`；
- Node.js 22+ 与 npm；
- Docker 与 Docker Compose；
- 可选：GNU Make。

Windows PowerShell 如果禁止执行 `npm.ps1`，可直接使用 `npm.cmd` 执行对应 npm 命令。

## 环境变量

复制示例配置：

```bash
cp .env.example .env
```

至少修改 `DJANGO_SECRET_KEY` 与 `POSTGRES_PASSWORD`。所有数据库时间以 UTC 保存；`DEFAULT_TIMEZONE` 使用 IANA 名称。任何密钥都不得放进 `VITE_*`，因为 Vite 变量会进入浏览器产物。

默认 PostgreSQL 镜像为官方的 `postgres:17-alpine`。如果所在网络无法稳定访问 Docker Hub，可在本地 `.env` 中覆盖镜像地址，例如：

```text
POSTGRES_IMAGE=docker.1ms.run/library/postgres:17-alpine
```

镜像加速源属于部署环境配置，仓库不强制绑定某个第三方服务。团队或生产环境应使用可信的企业镜像仓库，并可进一步按 digest 固定镜像。

## Docker 启动

```bash
docker compose up --build
```

入口地址为 `http://localhost:8080`。停止服务：

```bash
docker compose down
```

首次启动后执行 Django 和 LangGraph 持久化迁移：

```bash
docker compose exec django python manage.py migrate
docker compose exec django python manage.py setup_langgraph
```

## 本地启动

先启动依赖：

```bash
docker compose up -d postgres redis
```

后端依赖统一由 `uv` 管理：

```bash
cd backend
uv sync
uv run python manage.py migrate
uv run python manage.py setup_langgraph
uv run python manage.py runserver
```

另一个终端启动 Celery：

```bash
cd backend
uv run celery -A config worker --loglevel=INFO
uv run celery -A config beat --loglevel=INFO
```

前端：

```bash
cd frontend
npm install
npm run dev
```

Vite 默认把 `/api` 与 `/health` 代理到 `http://localhost:8000`。

## OpenAPI 契约

生成 Django Schema：

```bash
make api-schema
```

输出为 `backend/openapi.json`。生成前端 TypeScript 类型：

```bash
make frontend-api
```

输出为 `frontend/src/api/generated/schema.d.ts`。API 发生变化时必须同时更新 Schema 和前端类型，生成文件不应手工编辑。

## 测试与检查

| 命令 | 用途 |
| --- | --- |
| `make up` | 构建并启动全部 Compose 服务 |
| `make down` | 停止 Compose 服务 |
| `make build` | 构建容器镜像 |
| `make logs` | 持续查看容器日志 |
| `make backend-test` | 运行 pytest |
| `make frontend-test` | 运行 Vitest |
| `make lint` | 运行 Ruff、mypy 与 ESLint |
| `make check` | 运行主要后端与前端质量检查 |
| `make migrate` | 执行 Django 迁移 |
| `make migrations` | 检查是否存在未生成迁移 |
| `make api-schema` | 生成 OpenAPI JSON |
| `make frontend-api` | 生成 OpenAPI JSON 和前端类型 |

不使用 Make 时可直接运行：

```bash
cd backend
uv run python manage.py check --settings=config.settings.test
uv run pytest
uv run ruff check .
uv run mypy .

cd ../frontend
npm test
npm run lint
npm run build
```

Playwright 浏览器需要单独安装：

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

## 用户时间偏好 API

当前用户偏好端点：

```text
GET   /api/v1/preferences/me/
PATCH /api/v1/preferences/me/
```

端点使用 Django Session 或 DRF 支持的认证方式。写操作由 `UserPreferenceService` 执行，API Serializer 不直接保存 ORM 对象。前端入口为 `/settings/time`。

提醒端点：

```text
GET    /api/v1/reminders/
POST   /api/v1/reminders/
DELETE /api/v1/reminders/{id}/
```

删除操作执行状态机取消，不会物理删除提醒。前端入口为 `/reminders`。

日程与任务端点：

```text
GET|POST          /api/v1/events/
GET|PATCH|DELETE  /api/v1/events/{id}/
GET|POST          /api/v1/tasks/
GET|PATCH         /api/v1/tasks/{id}/
POST              /api/v1/tasks/{id}/complete/
GET               /api/v1/today/
```

事件 PATCH/DELETE 需要 `expected_version` 查询参数；DELETE 执行取消而非物理删除。

## 尚未实现

- Email、Telegram、Browser 等真实通知渠道；
- Time Steward Agent、Briefing Workflow 和外部日历同步；
- ActionProposal、HITL 与 Agent SSE；
- Briefing Workflow、天气、新闻和外部日历；
- 生产 TLS、完整监控、备份和发布流水线。

## 规范关系与注意事项

`PROJECT_SPEC.md` 描述完整后端和 Agent 架构，`FRONTEND_SPEC.md` 描述完整工作台体验。当前实现保持 PostgreSQL 权威数据、Application Service 写入、UTC 存储和 IANA 时区展示等边界。两份规范对职责边界没有实质冲突，路线图以开发指南给出的 Phase 0–10 编号统一后续交付。

development settings 允许本地调试，production settings 强制提供安全密钥；生产环境仍需进一步限制 Host、Cookie、TLS、静态文件与日志策略。Docker 构建依赖外部镜像和 Python/npm 包仓库。

## 下一步

Phase 4 已完成；下一阶段为 **Phase 5：使用 LangChain `create_agent()` 与内置 Middleware 实现受限的 Time Steward Agent**。
