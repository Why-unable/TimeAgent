# Time Agent 路线图

每个阶段必须可独立验收；未列入阶段目标的功能不应顺带实现。

当前进度：Phase 0、Phase 1 与 Phase 2 已完成；下一步进入 Phase 3 任务拆分。

## Phase 0：工程骨架

- 状态：已完成。
- 目标：建立可运行、可测试、可生成契约的 Monorepo。
- 后端：Django 三套 settings、PostgreSQL、Redis、Celery、健康检查、OpenAPI。
- 前端：React/Vite、路由、布局、状态页、统一 API Client、全局错误边界。
- 测试：健康检查、状态页、API Client、Django check、前后端静态检查与构建。
- 验收：Compose 配置有效；基础服务可启动；Schema 和前端类型可生成。
- 不包含：领域模型、认证业务、Agent、提醒、简报和外部 Provider。

## Phase 1：UserPreference 与时间基础

- 状态：已完成。
- 目标：建立全系统统一的用户时区和时间处理基础。
- 后端：UserPreference、IANA 时区校验、UTC 转换工具、Application Service。
- 前端：时区读取与展示、最小时间偏好表单、统一时间工具。
- 测试：UTC/本地时间转换、夏令时、无效时区、固定当前时间。
- 验收：用户时间可无歧义地转换、保存并按配置展示。
- 不包含：CalendarEvent、Task、Reminder、Agent。

## Phase 2：提醒完整闭环

- 状态：已完成。
- 目标：从提醒创建到确定性投递形成可靠闭环。
- 后端：Reminder、ReminderService、Dispatcher、Celery 重试、幂等、Console Provider。
- 前端：提醒列表、创建与取消、状态和失败原因展示。
- 测试：状态转换、重复投递、重试、时区、Worker 集成。
- 验收：到期提醒不经过 LLM 且不会重复发送。
- 不包含：外部通知渠道、Agent 自然语言创建。

## Phase 3：CalendarEvent、Task 与 Today 页面

- 目标：提供结构化事务管理和每日视图。
- 后端：CalendarEvent、Task、Services、冲突检查、REST API、Today 汇总。
- 前端：Today、Calendar 和 Tasks 的最小 CRUD 界面。
- 测试：模型、状态机、冲突、API、关键组件与 E2E。
- 验收：用户不依赖 Agent 即可查看和管理事务。
- 不包含：外部日历同步、复杂重复规则、Agent 操作。

## Phase 4：LangGraph 基础设施

- 目标：建立可持久化、可路由、可恢复的触发框架。
- 后端：TriggerEnvelope、RuntimeContext、AppState、Checkpointer、Store、Outer Graph。
- 前端：仅预留运行状态类型，不实现聊天业务。
- 测试：触发路由、持久化边界、中断恢复、调用限制基础设施。
- 验收：不同触发类型进入确定的工作流，提醒不进入 LLM。
- 不包含：Time Steward Agent、HITL、完整 SSE UI。

## Phase 5：Time Steward Agent

- 目标：用 `create_agent()` 实现受限的主 Agent 查询与低风险操作。
- 后端：只读 Tool、受控写 Tool、Middleware、审计、流式事件。
- 前端：最小 Chat、统一 SSE Client、Tool 状态和错误展示。
- 测试：固定评测集、Tool 选择、时区注入、调用上限、断线恢复。
- 验收：Agent 可查询真实业务数据且不能绕过 Service。
- 不包含：高风险写入直执行、多 Agent 自组织。

## Phase 6：ActionProposal 与 HITL

- 目标：让高风险操作透明、可编辑、可拒绝。
- 后端：ActionProposal、风险策略、审批 API、中断与恢复、审计。
- 前端：审批卡片、审批列表、编辑后批准和过期状态。
- 测试：批准、拒绝、过期、并发修改、幂等和执行失败。
- 验收：高风险写操作未经有效审批绝不执行。
- 不包含：自动批量审批、复杂 RBAC。

## Phase 7：Briefing Workflow

- 目标：建立确定性收集与 Agent 编辑相结合的简报流程。
- 后端：BriefingDefinition/Run、Registry、日历/任务 Section、Editor Agent、Handoff。
- 前端：简报配置、手动运行、结果与来源展示。
- 测试：Section 并行收集、部分失败、结构化输出、手动 Handoff。
- 验收：手动简报可生成、保存并展示，单 Section 失败可降级。
- 不包含：天气、新闻和定时自动投递。

## Phase 8：天气与新闻

- 目标：通过 Provider 扩展外部信息 Section。
- 后端：WeatherProvider、NewsProvider、去重、来源与时间校验。
- 前端：来源、警告、Provider 部分失败展示。
- 测试：Provider Mock、超时、降级、去重和来源保留。
- 验收：外部服务失败不导致整份简报丢失。
- 不包含：邮箱、外部日历、网页大规模抓取。

## Phase 9：外部日历和通知渠道

- 目标：接入可替换的日历同步和真实通知渠道。
- 后端：CalendarProvider、邮件/Telegram Provider、OAuth、同步与冲突处理。
- 前端：集成状态、授权回调、重新授权、通知设置。
- 测试：Token 过期、增量同步、版本冲突、通知失败重试。
- 验收：外部集成可断开替换，失败不会破坏本地权威数据。
- 不包含：自动修改他人日历、Gmail 自动回复。

## Phase 10：生产部署与监控

- 目标：形成可安全部署和观测的单体生产系统。
- 后端：结构化日志、Prometheus、备份、生产安全、性能与故障恢复。
- 前端：生产构建、错误追踪、缓存策略、响应式完善。
- 测试：容器集成、代理、升级回滚、备份恢复、基础负载和安全检查。
- 验收：具备 TLS、监控、告警、备份与可重复部署流程。
- 不包含：Kubernetes、微服务拆分、复杂多租户。

## 开发任务

原则上每个任务对应一个独立提交或 Pull Request。

| 编号 | 任务 | 阶段 |
| --- | --- | --- |
| T001 | 初始化 Monorepo 目录与开发文档 | Phase 0 |
| T002 | 初始化 Django 与三套 settings | Phase 0 |
| T003 | 使用 uv 配置并锁定后端依赖 | Phase 0 |
| T004 | 初始化 React、TypeScript 与 Vite | Phase 0 |
| T005 | 配置 PostgreSQL 和 Redis | Phase 0 |
| T006 | 配置 Celery Worker 与 Beat | Phase 0 |
| T007 | 实现 live/ready 健康检查 | Phase 0 |
| T008 | 建立前端 Layout、Router 与状态页 | Phase 0 |
| T009 | 建立统一 API Client 与 Query Provider | Phase 0 |
| T010 | 配置 OpenAPI Schema 与 TypeScript 生成 | Phase 0 |
| T011 | 配置 Docker Compose 与 Nginx | Phase 0 |
| T012 | 建立后端测试、Ruff 与 mypy | Phase 0 |
| T013 | 建立前端 Vitest、RTL 与 Playwright | Phase 0 |
| T014 | 编写 Phase 0 README 与 ADR | Phase 0 |
| T015 | 实现 UserPreference 模型与迁移 | Phase 1 |
| T016 | 实现统一 UTC/IANA 时间工具 | Phase 1 |
| T017 | 实现 UserPreference Service 与 API | Phase 1 |
| T018 | 实现前端用户时区读取与展示 | Phase 1 |
| T019 | 实现 Reminder 模型与状态机（已完成） | Phase 2 |
| T020 | 实现 ReminderService 与幂等创建（已完成） | Phase 2 |
| T021 | 实现 Reminder Dispatcher 与 Console Provider（已完成） | Phase 2 |
| T022 | 实现提醒 REST API 与前端列表（已完成） | Phase 2 |
