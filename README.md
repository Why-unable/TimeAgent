# TimeAgent

TimeAgent 是面向个人的时间管理助理。它把任务、日程、提醒和每日执行放在同一条工作流中：用户查看今天的重点，与助理讨论模糊目标，检查计划草案，并在高风险变更执行前作出确认。

## 项目概览

- **今天**：查看当前任务、后续安排、执行进度和每日收尾。
- **助理**：通过 Time Steward 对话查询信息、澄清意图和起草安排。
- **计划**：查看日历、任务和计划草案；手机端使用适合触控的日期导航与编辑面板。
- **提醒与简报**：通过确定性后台任务调度，提供状态可追踪的提醒和日程简报。
- **审批与记忆**：高风险变更需用户审批；时间偏好记忆由用户控制，仅作为建议背景。
- **Web 与 Android**：React Web 前端同时运行在 Capacitor Android WebView；Android APK 通过应用内更新服务分发。

## 架构与产品边界

```text
React / TypeScript / Vite ── REST / SSE ── Django / DRF
                                              │
                                   Application Services
                                              │
                                      PostgreSQL

Time Steward (LangChain create_agent) ── Tools ── Application Services
Celery Dispatcher ── reminders and scheduled briefings
Capacitor ── Android WebView and native device capabilities
```

- PostgreSQL 是业务事实的唯一权威来源；缓存、对话和记忆不替代业务数据。
- 写入经过 Application Service；时间以 UTC 保存，并按用户 IANA 时区解析和展示。
- Agent 通过受控 Tool 使用应用服务；高风险操作经 ActionProposal 和 HITL 审批。
- 提醒与定时简报由确定性 Celery 工作流触发，不依赖 LLM 调度。
- 外部能力通过 Provider 接口接入；前端不负责冲突、权限或业务状态判断。

## 技术栈

- **后端**：Python 3.12、Django 5.2、Django REST Framework、PostgreSQL、Redis、Celery、LangChain、LangGraph、uv。
- **前端**：React、TypeScript、Vite、TanStack Query、Tailwind CSS、Capacitor、npm。
- **运行与部署**：Docker Compose、Nginx；生产公网入口经 TLS 代理或 Cloudflare Tunnel。
- **质量保障**：pytest、Ruff、mypy、Vitest、React Testing Library、Playwright。

## 本地运行

需要 Python 3.12、uv、Node.js 22+、npm 和 Docker Compose。

```powershell
Copy-Item .env.example .env
# 配置本地密钥和模型设置后：
docker compose up -d --build
```

默认 Web 入口为 `http://localhost:8080`；健康检查为 `http://localhost:8080/health/ready`。如配置了 `TIME_AGENT_HTTP_PORT`，请使用对应端口。

常用检查：

```powershell
make check
make lint
cd frontend
npm run test:e2e
```

## 仓库结构

| 路径 | 内容 |
|---|---|
| `backend/` | Django 应用、Application Services、Agent、Celery 与后端测试 |
| `frontend/` | React 前端、Capacitor Android 工程、API 客户端与前端测试 |
| `infra/` | Nginx 等运行配置 |
| `docs/architecture/`、`docs/decisions/` | 架构说明与 ADR |
| `docs/mobile-ui/` | 移动端设计原则、Blueprint、验收清单和截图证据 |
| `docs/operations/` | 生产部署、备份、恢复、观测和发布记录 |
| `ROADMAP.md` | 项目阶段与当前交付范围 |

## 文档入口

- [项目路线图](ROADMAP.md)
- [开发与历史资料索引](docs/development/README.md)
- [移动端设计规范](docs/mobile-ui/README.md)
- [生产部署指南](docs/operations/linux-server-deployment.md)
- [运维与评测指南](docs/operations/observability-and-evaluation.md)

修改重要页面、业务边界或部署拓扑前，请先阅读对应 Blueprint、ADR 和仓库规则 [AGENTS.md](AGENTS.md)。
