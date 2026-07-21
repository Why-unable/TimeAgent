# Time Agent 路线图

每个阶段必须可独立验收；未列入阶段目标的功能不应顺带实现。

当前进度：Phase 0 至 Phase 8 已完成；下一阶段为 Phase 9。

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

- 状态：已完成。
- 目标：提供结构化事务管理和每日视图。
- 后端：CalendarEvent、Task、Services、冲突检查、REST API、Today 汇总。
- 前端：Today、Calendar 和 Tasks 的最小 CRUD 界面。
- 测试：模型、状态机、冲突、API、关键组件与 E2E。
- 验收：用户不依赖 Agent 即可查看和管理事务。
- 不包含：外部日历同步、复杂重复规则、Agent 操作。

## Phase 4：LangGraph 基础设施

- 状态：已完成。
- 目标：建立可持久化、可路由、可恢复的触发框架。
- 后端：TriggerEnvelope、RuntimeContext、AppState、Checkpointer、Store、Outer Graph。
- 前端：仅预留运行状态类型，不实现聊天业务。
- 测试：触发路由、持久化边界、中断恢复、调用限制基础设施。
- 验收：不同触发类型进入确定的工作流，提醒不进入 LLM。
- 不包含：Time Steward Agent、HITL、完整 SSE UI。

## Phase 5：Time Steward Agent

- 状态：已完成。
- 目标：用 `create_agent()` 实现受限的主 Agent 查询与低风险操作。
- 后端：只读 Tool、受控写 Tool、Middleware、审计、流式事件。
- 前端：最小 Chat、统一 SSE Client、Tool 状态和错误展示。
- 测试：固定评测集、Tool 选择、时区注入、调用上限、断线恢复。
- 验收：Agent 可查询真实业务数据且不能绕过 Service。
- 不包含：高风险写入直执行、多 Agent 自组织。

## Phase 6：ActionProposal 与 HITL

- 状态：已完成。
- 目标：让高风险操作透明、可编辑、可拒绝。
- 后端：ActionProposal、风险策略、审批 API、中断与恢复、审计，以及日程/提醒/任务的高风险软取消 Tool。
- 前端：审批卡片、审批列表、编辑后批准和过期状态。
- 测试：批准、拒绝、过期、并发修改、幂等和执行失败。
- 验收：高风险写操作未经有效审批绝不执行。
- 不包含：自动批量审批、复杂 RBAC。

## Phase 7：Briefing Workflow

- 状态：已完成。
- 目标：建立可审计、可 Handoff 的独立简报运行与交付流程。
- 后端：BriefingDefinition/Run、Briefing Agent、只读调研 Tool、结构化报告、Handoff。
- 前端：简报配置、手动运行、结果与来源展示。
- 测试：Agent Tool 循环、部分失败、结构化输出、有限修复、手动 Handoff。
- 验收：手动简报可按请求范围生成、保存并展示，单数据源失败可降级。
- 不包含：天气、新闻和定时自动投递。

## Phase 8：天气与新闻

- 状态：已完成。
- 目标：通过 Provider 和 Briefing Agent 只读 Tool 扩展外部信息调研。
- 后端：WeatherProvider、NewsProvider、去重、来源与时间校验。
- 前端：来源、警告、Provider 部分失败展示。
- 测试：Provider Mock、超时、降级、去重和来源保留。
- 验收：未知主题可在可信 Feed 目录回退检索，外部服务失败不导致整份简报丢失。
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
| T023 | 实现 CalendarEvent 模型、迁移与模型测试（已完成） | Phase 3 |
| T024 | 实现 Task 模型、状态机与模型测试（已完成） | Phase 3 |
| T025 | 实现 EventService 与 TaskService（已完成） | Phase 3 |
| T026 | 实现日程冲突检测与空闲时间搜索（已完成） | Phase 3 |
| T027 | 实现 CalendarEvent 与 Task REST API（已完成） | Phase 3 |
| T028 | 实现 Calendar 与 Tasks 前端页面（已完成） | Phase 3 |
| T029 | 实现 Today 汇总 API 与前端页面（已完成） | Phase 3 |
| T030 | 锁定 LangChain/LangGraph v1 依赖基线并记录 ADR（已完成） | Phase 4 |
| T031 | 实现 TriggerEnvelope、RuntimeContext 与 AppState（已完成） | Phase 4 |
| T032 | 接入 PostgreSQL Checkpointer 与 Store（已完成） | Phase 4 |
| T033 | 实现 Outer Graph 与确定性 Trigger Router（已完成） | Phase 4 |
| T034 | 实现中断恢复与 Graph 调用限制基础设施（已完成） | Phase 4 |
| T035 | 预留前端运行状态类型并完成 Phase 4 集成验收（已完成） | Phase 4 |
| T036 | 建立可信 Actor Runtime Context 与 Phase 5 架构决策（已完成） | Phase 5 |
| T037 | 实现 Time Steward 只读 Tool 套件（已完成） | Phase 5 |
| T038 | 实现低风险写入 Tool、幂等与风险策略（已完成） | Phase 5 |
| T039 | 使用 `create_agent()` 实现 Time Steward 并接入 Outer Graph（已完成） | Phase 5 |
| T040 | 接入调用限制、重试、摘要与动态 Tool Policy Middleware（已完成） | Phase 5 |
| T041 | 实现 Conversation、AgentRun 与审计闭环（已完成） | Phase 5 |
| T042 | 实现 Chat REST API 与 Agent Run 生命周期（已完成） | Phase 5 |
| T043 | 实现统一流事件协议、SSE 游标恢复与取消（已完成） | Phase 5 |
| T044 | 实现最小 Chat、统一 SSE Client 与 Tool 状态 UI（已完成） | Phase 5 |
| T045 | 建立固定 Agent 评测集并完成 Phase 5 集成验收（已完成） | Phase 5 |
| T046 | 实现 ActionProposal 模型、迁移与风险策略（已完成） | Phase 6 |
| T047 | 接入 HumanInTheLoopMiddleware、中断落库与等待审批状态（已完成） | Phase 6 |
| T048 | 实现审批 API、版本并发控制、决定幂等与过期策略（已完成） | Phase 6 |
| T049 | 实现 Command 恢复、Celery 执行和成功/失败审计（已完成） | Phase 6 |
| T050 | 实现审批列表、Chat 审批卡片和编辑后批准（已完成） | Phase 6 |
| T051 | 完成 OpenAPI、测试、ADR 与 Compose/E2E 验收（已完成） | Phase 6 |
| T052 | 实现 BriefingDefinition、BriefingRun、SectionRun 与迁移（已完成） | Phase 7 |
| T053 | 实现 Briefing Registry 与 Calendar/Task Section（已完成） | Phase 7 |
| T054 | 实现 Section 并行收集、部分失败和确定性降级（已完成） | Phase 7 |
| T055 | 实现结构化 Briefing Editor 与 Markdown 发布（已完成） | Phase 7 |
| T056 | 实现 Time Steward `Command.PARENT` Handoff 与消息协议（已完成） | Phase 7 |
| T057 | 实现简报配置、手动运行、结果与来源 API/页面（已完成） | Phase 7 |
| T058 | 实现普通聊天、手动简报和自动简报会话分类（已完成） | Phase 7 |
| T059 | 完成 OpenAPI、测试、ADR 与 Phase 7 验收（已完成） | Phase 7 |
| T060 | 实现 Open-Meteo WeatherProvider、地点解析与天气 Section（已完成） | Phase 8 |
| T061 | 建立可信 Feed 目录、主题别名与 RSS/Atom NewsProvider（已完成） | Phase 8 |
| T062 | 实现新闻时间过滤、规范化、排序、去重和 PostgreSQL 来源留存（已完成） | Phase 8 |
| T063 | 将天气与新闻纳入 Briefing Registry、Editor Schema 和确定性降级（已完成） | Phase 8 |
| T064 | 实现天气地点、新闻主题和 Provider 目录前端配置（已完成） | Phase 8 |
| T065 | 完成 OpenAPI、Provider Mock、超时降级、ADR 与 Phase 8 验收（已完成） | Phase 8 |
| T066 | 将固定 Section 收集重构为独立 Briefing Agent 与只读调研 Tool（已完成） | Phase 8 |
| T067 | 实现结构化委托、调研报告、完整性校验与一次有限修复（已完成） | Phase 8 |
| T068 | 实现天气 16 天范围和未知新闻主题可信目录回退检索（已完成） | Phase 8 |
| T069 | 接入外部 Tool 重试/错误降级 Middleware 并记录 ADR（已完成） | Phase 8 |
