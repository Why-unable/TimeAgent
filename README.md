# Time Agent

Time Agent 是以时间为核心的个人智能事务管理系统。本仓库当前已完成 **Phase 5**，具备提醒闭环、结构化事务管理、每日工作台，以及受限、可审计、可恢复的 Time Steward Agent。

> Time Steward 使用 LangChain `create_agent()`、LangGraph PostgreSQL 持久化和官方 Middleware；高风险写入、ActionProposal/HITL 与简报业务仍在后续阶段。

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
- 基于可信 Runtime Context 与 `ToolRuntime` 的 Time Steward Tool 套件，Tool 不直接访问 ORM。
- `create_agent()` 模型—工具循环，以及调用限制、重试、错误处理、摘要、动态 Tool Policy 和审计 Middleware。
- 低风险事件/任务/提醒写入、只读查询、冲突检测和空闲时间搜索；高风险 Tool 不注册。
- Conversation、AgentRun、ToolCallAudit、Celery 后台 Agent 执行、统一 AgentEvent 与取消 API。
- `/chat/:conversationId` 稳定会话 URL、历史会话列表与回载、新建聊天、实时 SSE 增量、断线游标续传、Tool 生命周期和错误状态展示。

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

至少修改 `DJANGO_SECRET_KEY` 与 `POSTGRES_PASSWORD`。运行 Time Steward 还需配置
`AGENT_API_KEY`。模型、Graph 和 Middleware 的非敏感配置统一位于
`backend/config/agent.example.yaml`；可复制为被 Git 忽略的 `backend/config/agent.yaml`，并设置
`TIME_AGENT_CONFIG_PATH=config/agent.yaml`。API Key 等密钥仍只保存在 `.env`，YAML 通过
`$AGENT_API_KEY` 引用。所有数据库时间以 UTC 保存；`DEFAULT_TIMEZONE` 使用 IANA 名称。任何
密钥都不得放进 `VITE_*`，因为 Vite 变量会进入浏览器产物。

Agent 配置在进程启动后缓存，修改后需要重启 Django/Celery。配置由 Pydantic 严格校验，未知
字段、过期 `config_version`、不存在的模型别名和无效限制都会阻止 Agent 启动。当前模型适配器
显式支持 `openai_compatible`（DeepSeek 等 OpenAI 协议服务）和 `anthropic`（Claude 原生
Messages API），不会从 YAML 动态导入任意 Python 对象。Anthropic-compatible 中转站的
`base_url` 应填写 API root，不要带尾部 `/v1`；如中转站返回非标准 usage stream，可设置
`stream_usage: false`，保留 token 流式输出。详见
`docs/architecture/agent-configuration.md`。

可以在启动前验证配置（不会输出 API Key）：

```bash
cd backend
uv run python manage.py check_agent_config
```

发布 Phase 5 Agent 变更前，可用当前真实模型运行固定 Tool 轨迹评测：

```bash
cd backend
uv run python manage.py evaluate_time_steward
```

该命令会产生真实模型调用费用，但所有评测业务写入都会回滚。可使用 `--model claude` 或
`--model deepseek` 验证指定 Provider。模型自动回退顺序由 `agent.fallback_models` 配置。

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

如果构建阶段卡在或失败于 `ghcr.io/astral-sh/uv:*`、`python:*`、`node:*` 等基础镜像元数据拉取，
通常是本机到对应镜像仓库的网络问题，而不是应用启动失败。后端基础镜像可在本地 `.env` 中覆盖，
例如：

```text
UV_IMAGE=docker.1ms.run/ghcr.io/astral-sh/uv:0.11.29
PYTHON_IMAGE=docker.1ms.run/library/python:3.12-slim
NODE_IMAGE=docker.1ms.run/library/node:24-alpine
FRONTEND_NGINX_IMAGE=docker.1ms.run/library/nginx:1.28-alpine
NGINX_IMAGE=docker.1ms.run/library/nginx:1.28-alpine
```

如果镜像已经在本机成功构建过，只想按当前镜像启动，也可以先使用：

```bash
docker compose up -d
```

开发过程中修改代码后，需要按改动范围重新构建对应镜像。Nginx 应在上游容器重建后重启，
以重新解析 Django 或前端容器地址：

```bash
# 仅前端
docker compose up -d --build frontend
docker compose restart nginx

# 仅 Django 后端
docker compose up -d --build django
docker compose restart nginx

# Agent、Celery Task 或共享后端代码
docker compose up -d --build django celery-worker celery-beat
docker compose restart nginx
```

前端镜像更新后，在浏览器执行 `Ctrl + F5` 强制刷新。可以使用以下命令确认服务状态并检查
最近日志：

```bash
docker compose ps
docker compose logs --tail=100 django frontend nginx
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
GET|POST          /api/v1/chat/conversations/
GET               /api/v1/chat/conversations/{id}/
POST              /api/v1/chat/messages/
GET               /api/v1/chat/runs/{id}/
POST              /api/v1/chat/runs/{id}/cancel/
GET               /api/v1/chat/runs/{id}/events/
```

事件 PATCH/DELETE 需要 `expected_version` 查询参数；DELETE 执行取消而非物理删除。

## 尚未实现

- Email、Telegram、Browser 等真实通知渠道；
- Briefing Workflow 和外部日历同步；
- ActionProposal 与 HITL；
- Briefing Workflow、天气、新闻和外部日历；
- 生产 TLS、完整监控、备份和发布流水线。

## 规范关系与注意事项

`PROJECT_SPEC.md` 描述完整后端和 Agent 架构，`FRONTEND_SPEC.md` 描述完整工作台体验。当前实现保持 PostgreSQL 权威数据、Application Service 写入、UTC 存储和 IANA 时区展示等边界。两份规范对职责边界没有实质冲突，路线图以开发指南给出的 Phase 0–10 编号统一后续交付。

development settings 允许本地调试，production settings 强制提供安全密钥；生产环境仍需进一步限制 Host、Cookie、TLS、静态文件与日志策略。Docker 构建依赖外部镜像和 Python/npm 包仓库。

## 下一步

Phase 5 已完成；下一阶段为 **Phase 6：ActionProposal 与 HITL 高风险操作审批闭环**。
