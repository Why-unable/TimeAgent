# Time Agent

## Phase 10：观测、备份与恢复

生产日志为 JSON，每个 HTTP 响应均携带 `X-Request-ID`；它可用于将浏览器报错、Nginx 请求和 Django 完成日志关联起来。日志不会记录查询参数、Cookie、请求正文、密钥或用户对话内容。

Prometheus 是可选的本机监控覆盖层，不通过 Cloudflare Tunnel 暴露。启动后访问 `http://localhost:9090` 查看目标状态与告警规则：

```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.observability.yml up -d prometheus
# 或：make observability
```

若 Docker Hub 在本机网络中不可达，可在 `.env` 通过 `PROMETHEUS_IMAGE` 覆盖为团队已验证的镜像地址；仓库默认不会绑定任何第三方镜像加速服务。

它在 Docker 内网抓取 Django 的 `/metrics`；公网入口对该路径返回 404。默认告警涵盖 Django 目标不可达与持续的 HTTP 5xx。将 Prometheus 接入 Alertmanager、邮件或其他告警渠道前，应先在本机确认告警规则符合实际运维策略。

PostgreSQL 使用 custom-format 备份，备份文件默认写入被 Git 忽略的 `backups/`。建议定期将备份复制到独立、加密且有保留策略的存储：

```powershell
.\scripts\backup-postgres.ps1
.\scripts\backup-postgres.ps1 -OutputDirectory D:\TimeAgentBackups
```

恢复会覆盖归档包含的对象，因此只允许显式确认后执行；请先针对隔离的非生产 Compose 项目完成恢复演练：

```powershell
.\scripts\restore-postgres.ps1 -ArchivePath .\backups\time-agent-YYYYMMDD-HHMMSS.dump -ConfirmRestore
```

部署前后最低限度检查：

```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
Invoke-WebRequest http://localhost:8080/health/ready
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=100 django nginx celery-worker
```

Time Agent 是以时间为核心的个人智能事务管理系统。本仓库当前已完成 **Phase 9**，具备提醒闭环、结构化事务管理、每日工作台、可恢复的 Time Steward Agent、高风险操作审批、天气与新闻简报，以及持久化的 Console/Email/Web Push 通知投递体系。

> Time Steward 使用 LangChain `create_agent()`、LangGraph PostgreSQL 持久化和官方 Middleware；高风险写入通过 ActionProposal/HITL 审批；Briefing Workflow 使用确定性并行 Section、受限 Editor 和结构化输出。

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
- 基于可信 Runtime Context 与 `ToolRuntime` 的 Time Steward Tool 套件，支持查询、创建、任务进度以及日程/提醒/任务的软取消，Tool 不直接访问 ORM。
- `create_agent()` 模型—工具循环，以及调用限制、重试、错误处理、摘要、动态 Tool Policy 和审计 Middleware。
- 低风险任务/提醒创建与任务进度操作、只读查询、冲突检测和空闲时间搜索；高风险 Tool 通过显式策略注册。
- Conversation、AgentRun、ToolCallAudit、Celery 后台 Agent 执行、统一 AgentEvent 与取消 API。
- `/chat/:conversationId` 稳定会话 URL、历史会话列表与回载、新建聊天、实时 SSE 增量、断线游标续传、Tool 生命周期和错误状态展示。
- ActionProposal PostgreSQL 领域模型、风险策略、有效期、版本控制、决定幂等和完整执行审计。
- LangChain 官方 `HumanInTheLoopMiddleware`、LangGraph interrupt 与同一 thread 的 `Command(resume=...)` 恢复。
- `create_event` 支持批准、编辑后批准或拒绝；`cancel_event`、`cancel_reminder`、`cancel_task` 仅支持批准或拒绝，且未经审批都不会进入 Tool/Application Service。
- 审批 REST API、`/approvals` 集中列表、Chat 内结构化审批卡片、冲突信息和过期/失败状态。
- Celery Beat 自动过期审批，并以安全拒绝语义恢复暂停的 AgentRun。
- BriefingDefinition、BriefingRun 与逐 Section 运行记录，保留配置快照、来源、警告、模型配置和最终结构化结果。
- 短生命周期 Briefing Agent、日程/任务/天气/新闻只读调研 Tool、有限失败恢复、确定性来源校验、Markdown 渲染和 SSE 分块发布。
- Time Steward 通过 `Command.PARENT` Handoff 转交自然语言简报请求；最终消息序列保持有效的 AI tool call、ToolMessage 和简报 AIMessage。
- `/briefings` 支持配置、手动运行、结果、来源和“在聊天中继续”；聊天历史按普通聊天、手动简报和自动简报分类。
- `NotificationDelivery` 状态机、稳定幂等键、Celery 异步投递/有限重试/中断恢复，以及统一 Console、Django Email 和 Web Push Provider Registry；Reminder 和 Briefing 的各渠道结果独立审计。
- `/settings/notifications` 支持当前用户 Email/Push 渠道开关、显式浏览器权限申请、Subscription 创建/取消和最近投递状态；VAPID 私钥不进入前端。
- 外部日历已建立 Provider Protocol、Pydantic DTO、能力声明和统一异常契约；尚未实现任何 OAuth、Token、供应商接入或同步。

## 计划事务与提醒

- 任务是待完成的工作，可设置计划开始/结束时间；日程是实际占用的一段时间。一个任务可关联多条日程，日程也可独立存在。
- 有计划开始时间的任务会维护未来的提前 7 天、3 天、1 天和 30 分钟提醒；日程维护提前 1 天、2 小时和 30 分钟提醒。重排会更新未投递提醒，完成或取消会取消未投递提醒。
- 手工提醒可关联任务、日程或独立存在。通知仍由 Celery Dispatcher 和已启用的 Console、Email、Web Push 渠道投递，不经过 LLM。
- “默认事件时长”仅用于新建日程时预填结束时间；它不会修改既有日程或提醒。日程的“公开/私密”目前是未来共享日历的预留字段，当前仍只允许所有者访问。

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

ActionProposal 默认 24 小时过期，可用 `ACTION_PROPOSAL_TTL_SECONDS` 调整。过期只会拒绝待执行 Tool，不会自动批准或产生业务写入。

Agent 配置在进程启动后缓存，修改后需要重启 Django/Celery。配置由 Pydantic 严格校验，未知
字段、过期 `config_version`、不存在的模型别名和无效限制都会阻止 Agent 启动。当前模型适配器
显式支持 `openai_compatible`（DeepSeek 等 OpenAI 协议服务）和 `anthropic`（Claude 原生
Messages API），不会从 YAML 动态导入任意 Python 对象。Anthropic-compatible 中转站的
`base_url` 应填写 API root，不要带尾部 `/v1`；如中转站返回非标准 usage stream，可设置
`stream_usage: false`，保留 token 流式输出。详见
`docs/architecture/agent-configuration.md`。

Briefing Agent 的模型由 `agent.briefing_model` 指定；未设置时继承
`agent.default_model`。它拥有日程、任务、天气、新闻等只读调研 Tool，不拥有任何业务写入
Tool；每次简报都是不持久化内部对话的短生命周期 Agent Run。外部 Tool 使用有限重试，最终
简报、来源、调研摘要、失败项和未满足要求会持久化到 `BriefingRun`。

Briefing Agent 直接把 `BriefingAgentReport` Schema 传给 LangChain `create_agent()`：模型
支持原生结构化输出时自动使用 `ProviderStrategy`，否则使用 `ToolStrategy`。DeepSeek 配置中的
`enable_thinking: false` 会映射为官方 OpenAI-compatible 请求体
`thinking: {type: disabled}`，从而允许 `ToolStrategy` 强制提交最终报告。若 Anthropic-compatible
中转站无法承载完整原生 JSON Grammar，可设置 `structured_output_strategy: tool`，LangChain
将继续通过官方 `ToolStrategy` 返回同一个 Pydantic 类型。

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

## 浏览器账户与 PWA 登录

应用使用 Django 同域 Session，不使用保存在浏览器 Local Storage 的 JWT。首次打开
受保护页面会跳转到 `/login`；登录页支持邮箱注册、登录和通过邮件重置密码。登录成功后
会回到原先请求的页面，账户设置位于 `/settings/account`。管理员后台 `/admin/` 只用于
运维，不是普通用户登录入口。

注册接口带有 CSRF 保护和匿名访问频率限制。公开部署前请确认 `.env` 中的
`AUTH_REGISTRATION_ENABLED` 是否符合预期；个人或邀请制部署可在首个账户创建后设为
`false`。

## Cloudflare Tunnel 生产运行

Cloudflare Tunnel 负责公网 HTTPS，Docker 内部入口只使用 HTTP。请在 `.env` 中配置实际
域名，且不要将任何密码、API Key 或 Tunnel Token 提交到 Git：

```env
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=use-a-unique-random-secret
DJANGO_ALLOWED_HOSTS=steward.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://steward.example.com
SESSION_COOKIE_SECURE=true
CSRF_COOKIE_SECURE=true
AUTH_REGISTRATION_ENABLED=true
```

首次部署或更新时使用生产覆盖文件。它会将 Nginx 仅绑定至 `127.0.0.1:8080`，因此
Cloudflare Tunnel 的 Service URL 仍应为 `http://localhost:8080`：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

发布前显式执行迁移，随后检查公开健康端点：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec django python manage.py migrate --noinput
curl https://steward.example.com/health/ready
```

`docker-compose.prod.yml` 使用 Uvicorn ASGI，而不是 Django `runserver`。确认 HTTPS 稳定
运行一段时间后，才应考虑设置不可轻易撤销的 HSTS 参数 `SECURE_HSTS_SECONDS`。

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

docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.observability.yml up -d --build django celery-worker celery-beat
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
GET               /api/v1/action-proposals/
GET               /api/v1/action-proposals/{id}/
POST              /api/v1/action-proposals/{id}/approve/
POST              /api/v1/action-proposals/{id}/edit/
POST              /api/v1/action-proposals/{id}/reject/
GET|POST          /api/v1/briefings/definitions/
GET|PATCH         /api/v1/briefings/definitions/{id}/
GET|POST          /api/v1/briefings/runs/
GET               /api/v1/briefings/runs/{id}/
GET               /api/v1/providers/catalog/
```

事件 PATCH/DELETE 需要 `expected_version` 查询参数；DELETE 执行取消而非物理删除。

## 天气与新闻 Provider

Phase 8 默认使用 Open-Meteo 天气 API，以及服务端维护的可信 RSS/Atom Feed 目录。非敏感配置位于 `backend/config/providers.yaml`，可通过 `TIME_AGENT_PROVIDER_CONFIG_PATH` 指向另一份配置文件。默认目录包含 OpenAI News、GitHub、Python Insider、BBC World、NASA，以及中国新闻网、InfoQ 中文、量子位、开源中国、Solidot、爱范儿和 36氪等国内来源；所有地址必须使用 HTTPS。

用户不需要配置 Feed URL。在 `/settings/time` 中填写天气地点和新闻主题即可，例如 `上海` 与 `人工智能, 国内财经, Python`。后端会把别名归一为规范主题，选择覆盖这些主题的 Feed，再按主题命中、Feed 优先级和发布时间排序；目录未覆盖的主题会作为简报警告显示，不会自动扩大为任意网页搜索。同一次运行以受限线程池并发抓取 Feed，结果仍按目录顺序和评分确定性归并。

修改 Provider 配置后需重启 Django 和 Celery 服务。可在后端执行只读连通性检查：

```bash
cd backend
uv run python manage.py check_external_providers --weather-location 上海 --topic 人工智能 --topic Python
```

外部条目会保留来源 URL、发布方与时间；新闻规范化结果写入 PostgreSQL 并进行稳定指纹去重。单个 Provider/Feed 失败只会让简报进入部分降级，不会丢失日程和任务部分。

通知渠道通过 `.env` 配置。开发环境默认使用 Console 通知与 Django console Email Backend；SMTP 可通过 `EMAIL_BACKEND`、`EMAIL_HOST`、`EMAIL_PORT`、`EMAIL_USERNAME`、`EMAIL_PASSWORD`、TLS/SSL 和 `EMAIL_FROM_ADDRESS` 切换。Web Push 使用 `WEB_PUSH_VAPID_PUBLIC_KEY`、`WEB_PUSH_VAPID_PRIVATE_KEY` 和 `WEB_PUSH_VAPID_SUBJECT`。私钥只注入 Django/Celery，前端通过认证 API 读取公钥。修改后请重建 Django、Worker 和 Beat：

定时简报在“通知设置”中显式开启并设置每日发送时间，默认关闭。Celery Beat 每分钟按用户 IANA 时区扫描：发送时间前 5 分钟创建幂等的 `scheduled_briefing` AgentRun，并直接进入 Briefing Workflow；生成结果先保存到 PostgreSQL，再创建计划发送时间为整点的 NotificationDelivery。现有通知 Dispatcher 到期后通过用户已启用的简报 Email/Web Push 渠道投递。若服务在计划生成时刻短暂不可用，会在发送时间后 1 小时内补偿生成；同一用户、同一发送时刻只会创建一个 Run。

```powershell
docker compose up -d --build django celery-worker celery-beat frontend
docker compose restart nginx
```

生产 Web Push 必须使用 HTTPS；localhost 可用于开发。真实 SMTP/Web Push 测试默认不执行，只有在使用专用测试凭据并显式设置 `RUN_LIVE_NOTIFICATION_TESTS=1` 时才允许运行。

## 尚未实现

- Telegram、SMS、任意第三方收件人通知；
- 外部日历供应商、OAuth、Token、事件映射和同步；
- 定时自动简报投递调度（简报结果的通知投递能力已具备）；
- 生产 TLS、完整监控、备份和发布流水线。

## 规范关系与注意事项

`PROJECT_SPEC.md` 描述完整后端和 Agent 架构，`FRONTEND_SPEC.md` 描述完整工作台体验。当前实现保持 PostgreSQL 权威数据、Application Service 写入、UTC 存储和 IANA 时区展示等边界。两份规范对职责边界没有实质冲突，路线图以开发指南给出的 Phase 0–10 编号统一后续交付。

development settings 允许本地调试，production settings 强制提供安全密钥；生产环境仍需进一步限制 Host、Cookie、TLS、静态文件与日志策略。Docker 构建依赖外部镜像和 Python/npm 包仓库。

## 下一步

Phase 9 已完成；下一阶段为 **Phase 10：生产部署与监控**。
