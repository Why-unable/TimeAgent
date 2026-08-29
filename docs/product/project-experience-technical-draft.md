# Time Agent 项目经历技术底稿

> 更新日期：2026-08-25  
> 用途：从代码、配置、测试、ADR、运行记录与 Git 历史中提炼项目事实，为后续简历和面试准备提供证据。  
> 口径：本文不是产品宣传稿。`已实现` 仅表示代码与本地测试链路存在；`已验证` 需要实际运行证据；缺少真实数据、外部账号或设备的项目统一标为 `需要补测` / `NOT VERIFIED`。

## 0. 结论先行

Time Agent 不是一个把日历 CRUD 包在聊天框里的 Demo，而是一个以 PostgreSQL 业务事实为核心、将 LLM 语义能力与确定性时间系统分层的个人时间管理系统。系统已经形成四条主要闭环：

1. 用户通过 Web、Capacitor Android 或 Time Steward Agent 管理日程、任务与提醒；所有写入最终进入 Application Service 和 PostgreSQL。
2. Time Steward 用 LangChain `create_agent()` 完成自然语言理解、Tool 选择和结果解释；外层 LangGraph 只负责 Trigger 路由、Briefing Handoff、HITL 中断恢复与持久化边界。
3. Celery 负责到期提醒、简报、洞察扫描、Memory 重建和外部日历轮询；计时、冲突、排程、权限、幂等和通知策略均不交给 LLM。
4. Phase A-E 已把执行证据、个人估时、容量预测、计划草案、洞察收件箱和受控局部重排接入 API、前端及部分 Agent Tool，但真实用户收益、真实 Google/通知 Provider、Android 真机和生产负载仍未完成验收。

最值得讲的不是“用了 LangGraph”，而是如何把一个有写权限的 Agent 约束成可审计、可恢复、可回滚、时间语义确定的业务系统。

## 1. 项目定义与背景

### 1.1 面向场景与用户

面向需要同时管理会议、任务、截止时间、提醒和外部信息的个人知识工作者、学生与自由职业者。核心问题不是缺少待办列表，而是：

- 信息分散在日历、任务、提醒和外部日历中，用户难以看到完整的时间承诺；
- “有空”不等于“能完成”，传统日历缺少任务时长、截止时间、容量和计划/实际差异；
- 计划发生变化后，重新寻找可行时间和维护计划本身成本较高；
- 通用聊天模型能理解自然语言，但不能可靠计时、持久保存事实或保证写操作只执行一次；
- 主动提醒和自动重排若缺少配额、审批、撤销和证据，会迅速损害信任。

证据：`PROJECT_SPEC.md` 第 1、2 节，`docs/product/ai-native-time-agent-strategy.md` 第 1、3、4 节。

### 1.2 系统解决的问题

- 结构化管理 `CalendarEvent`、`Task`、`Reminder`，支持冲突检测、空闲时间搜索、Today 汇总和状态机；
- 用自然语言查询与操作真实业务数据，而不是让模型把聊天上下文当数据库；
- 将高风险写入转换为 `ActionProposal`，审批后恢复同一 Agent thread；
- 生成包含日程、任务、天气和新闻的可审计 Briefing，并支持每天定时投递；
- 记录任务开始/暂停/完成/跳过事实，给个人估时、容量预测和计划改进提供证据；
- 对截止风险和容量风险生成去重、可过期、可关闭的 `TemporalInsight`；
- 对被打断的计划提供受授权、可预览、可撤销的局部重排。

### 1.3 为什么需要“混合智能”架构

时间系统同时包含两类问题：

- 适合模型：模糊意图理解、信息澄清、Tool 路由、跨数据源综合、自然语言解释；
- 必须确定性实现：UTC/IANA 转换、DST、半开区间冲突、权限、状态机、幂等、审批、调度、通知配额和事务回滚。

因此系统的产品定义是“自然语言交互层 + 可靠事务系统 + 确定性调度/规划 + 受控 Agent”，不是端到端 LLM 日历。

## 2. 整体系统架构

### 2.1 模块划分

| 层次 | 主要模块 | 职责与证据 |
| --- | --- | --- |
| 客户端 | React 19、Vite、React Router、TanStack Query、Zustand、FullCalendar | 页面、缓存和 SSE 展示；统一请求入口为 `frontend/src/api/client.ts` |
| Android | Capacitor Shell + 原生 Kotlin/Java Plugin | Token 安全存储、本地通知、Deep Link、自托管 APK 更新；代码位于 `frontend/android/`、`frontend/src/native/` |
| API | Django 5.2 + DRF + drf-spectacular | `/api/v1/` 资源与动作 API、Session/Token 双认证、OpenAPI 契约 |
| Application | 各 app 的 `services.py` | 写入、事务、权限、幂等、乐观锁、业务状态机；Tool/View 不直接写 ORM |
| Domain/Data | Django models + PostgreSQL 17 | 日程、任务、提醒、运行、审批、通知、洞察、同步连接等权威事实 |
| Agent | `apps.agents` | Time Steward、RuntimeContext、Middleware、Tool、审计和 SSE 运行 |
| Workflow | Outer LangGraph、Briefing Workflow | Trigger 路由、Handoff、interrupt/resume、确定性简报边界 |
| Background | Celery Worker + Beat + Redis 7 | 提醒投递、简报调度、洞察扫描、Memory 重建、外部日历轮询 |
| External | Model/Weather/News/Calendar/Notification Providers | 可替换 Provider 接口，失败可降级；Google Calendar 当前只读 |
| Operations | Docker Compose、Nginx、Cloudflare Tunnel、Prometheus/Grafana/Loki | 部署、反代、SSE、日志、指标、告警、备份恢复 |

### 2.2 Agent / RAG / Tool / Model / Database / Backend 的关系

- **Model**：通过 `backend/apps/agents/model.py` 从严格校验的 `agent.yaml` 构建；当前支持 OpenAI-compatible 与 Anthropic 接口。
- **Agent**：`build_time_steward_agent()` 必须调用 LangChain `create_agent()`；内部模型-工具循环由框架负责。
- **Tool**：注册表 `TIME_STEWARD_TOOLS` 当前实际暴露 40 个 Tool，覆盖时间、日程、任务、提醒、规划、Decision Profile、外部日历状态、洞察和 Briefing Handoff。代码中共有 45 个 `@tool` 定义，其中部分细粒度 Event Tool 被 `mutate_events` 组合入口封装，并不直接暴露。
- **Backend Service**：Tool 通过 `require_actor/require_writable` 从可信 `RuntimeContext` 获取用户，再调用对应 Service；例如 `recommend_task_duration -> DecisionProfileService.recommend_duration`，`apply_local_replan -> AdaptivePlanningService`。
- **Database**：PostgreSQL 是业务事实唯一来源；LangGraph Checkpointer 保存 Agent thread 状态，Store 保存可重建 Time Memory，它们不能替代业务表。
- **RAG**：项目当前没有向量数据库、Embedding 检索或通用文档 RAG。Memory 是从 PostgreSQL 时间事实确定性统计、排序并在 Token 预算内注入；天气/新闻/日历是结构化 Provider/Tool 查询。简历中不应写“搭建 RAG 系统”。

### 2.3 用户消息的一次完整调用链

```text
React/Android Chat
  -> POST /api/v1/chat/...                     conversations/views.py
  -> AgentRunService 创建 Conversation/AgentRun
  -> Celery 后台执行
  -> TriggerEnvelope(user_message)
  -> OuterGraphRuntime / route_trigger           agents/outer_graph.py
  -> Time Steward create_agent()
  -> Runtime/Memory/Policy/Limit/Retry/Audit Middleware
  -> Model 选择 Tool
  -> Tool -> Application Service -> ORM -> PostgreSQL
  -> ToolMessage 返回模型
  -> 最终 AIMessage / ToolCallAudit / AgentEvent 落库
  -> SSE 按游标推送到前端，可断线续传或取消
```

若 Tool 命中高风险策略：

```text
Tool Call
  -> HumanInTheLoopMiddleware
  -> LangGraph interrupt
  -> ActionProposalService 持久化 proposal
  -> AgentRun = waiting_for_approval
  -> 用户 approve/edit/reject
  -> Command(resume=decision) 恢复同一 thread
  -> Tool -> Service -> PostgreSQL
```

证据：`backend/apps/agents/agents/time_steward.py`、`outer_graph.py`、`middleware.py`，`backend/apps/action_proposals/services.py`，`backend/apps/conversations/services.py` / `views.py`。

### 2.4 定时提醒与简报调用链

提醒链路完全不调用 LLM：

```text
Celery Beat -> ReminderDispatcher 扫描到期提醒
  -> 幂等 claim -> NotificationService
  -> Console/Email/WebPush Provider
  -> NotificationDelivery 状态与重试审计
```

定时简报也不先经过 Time Steward：

```text
Celery Beat -> DailyBriefingScheduler / evening scheduler
  -> Briefing Workflow
  -> 短生命周期 Briefing Agent（只读 research Tool）
  -> BriefingRun/SectionRun/来源/警告落库
  -> NotificationDelivery
```

证据：`backend/apps/reminders/dispatcher.py`、`backend/apps/briefings/tasks.py`、`workflow.py`、`agent.py`、`backend/apps/notifications/services.py`。

## 3. 个人核心贡献

### 3.1 归属证据与使用边界

Git 历史目前有 27 个提交，作者名为 `Why-unable` 或 `hugh`，但邮箱均为 `quenlin166@gmail.com`；从仓库证据看是同一开发身份持续完成 Phase 0-10。当前 Phase A-E 大量实现仍在工作区、尚未形成提交，所以“由我独立完成”的精确归属必须在提交或 PR 证据固化后再写入正式简历。

下面列的是**项目级核心贡献候选**，优先级按设计复杂度与面试价值排序，不是普通功能清单。

### 3.2 值得主张的核心工作

1. **设计 Agent 与事务系统的可信边界**  
   将 `Tool -> Application Service -> ORM` 固化为工程规则；建立 `RuntimeContext` 身份、动态 Tool Policy、调用上限、审计和安全退出，避免 Agent 绕过权限与业务规则。

2. **实现可恢复的高风险操作审批闭环**  
   用 `HumanInTheLoopMiddleware + LangGraph interrupt + PostgreSQL ActionProposal + Command(resume)` 把高风险 Tool 暂停、审批、编辑后批准、拒绝、过期和失败执行串成同一条可审计轨迹。

3. **解决相对时间在异步 Agent 中的不确定性**  
   将 run anchor 固化在可信 RuntimeContext，所有相对时间解析依赖显式 UTC 时间和用户 IANA 时区；多轮运行会为新一轮刷新锚点，同时保留同一轮内的一致性。对应提交 `779435d fix(agent): make relative event time deterministic` 与 ADR 0021。

4. **构建确定性规划与受控自适应链路**  
   从 first-fit baseline 演进到 planner v2：硬约束、未安排原因、约束快照、计划 TTL/版本、比较、局部重生成、锁定、应用前重验、HITL 应用，以及带 Automation Policy 和撤销批次的局部重排。

5. **建立从执行证据到个人时间决策的闭环**  
   以不可变 `TaskExecutionSignal` 记录实际行为；用时间衰减、最小样本门槛、语义/显式分组和置信度生成 Duration Recommendation，再将高置信 Profile 作为 Planner 软输入，并采集“准确/太短/太长”反馈。

6. **建设面向生产的异步与可观测基础**  
   实现 SSE 断线游标续传、Celery 确定性任务、通知幂等与重试、JSON 日志/X-Request-ID、脱敏 `LLMCallAudit`、Prometheus 低基数指标及 Grafana/Loki/Alertmanager overlay。

7. **完成 Web/Android 共用产品链路与自托管发布**  
   使用同一 React 构建服务 Web 和 Capacitor Android，区分 Session/CSRF 与 Native Token Auth；原生更新器验证 HTTPS、大小、SHA-256、package、versionCode/versionName 与签名，再交给系统安装器。

## 4. 核心技术实现

### 4.1 Time Steward Agent

第一层：`build_time_steward_agent()` 使用 LangChain `create_agent()`，传入 40 个注册 Tool、`TimeStewardState`、`RuntimeContext`、PostgreSQL Checkpointer/Store 和 Middleware 链。  
第二层：Middleware 在每次模型/工具调用周围注入动态 Prompt、Memory、HITL、调用预算、Retry/Fallback、错误转换、Tool 审计和 LLM 用量审计。模型只得到当前策略允许的 Tool，身份不从 Prompt 推断。

配置默认边界来自 `backend/config/agent.example.yaml`：Graph recursion limit 50、max concurrency 4、单轮模型调用 8、Tool 调用 16、模型/Tool 重试各 2；24 条消息触发摘要并保留 12 条。它们是配置默认值，不代表性能指标。

### 4.2 Workflow 与 Handoff

第一层：`OuterGraphRuntime` 维护 persistent/stateless 两套图；`reminder_due` 走无状态确定性路径，用户消息、审批与 Briefing 使用持久图。  
第二层：`transfer_to_briefing` 返回 `Command.PARENT`，把规范化请求和合法的 AI/Tool 消息序列交给父图的 `briefing_workflow`；外层图不重复实现 Agent 内部 planning loop。

Briefing Agent 也是 `create_agent()`，但生命周期短、无长期 Checkpointer，只暴露 calendar/task/weather/news/source catalog 五类只读 Tool，并用 `BriefingAgentReport` 结构化输出；执行校验失败时做有限修复或确定性 fallback。

### 4.3 Tool Calling 与风险策略

第一层：Tool 参数由 LangChain Schema 约束，`ToolRuntime` 提供 actor、run anchor、timezone、request ID、run ID 和 Store。  
第二层：只读 Tool 与写 Tool 分组；动态 Policy 根据用户偏好、冲突预检和工具风险决定直接执行或中断。批量日程通过 `mutate_events` 收敛入口，减少模型在多个细粒度写 Tool 之间误选。

所有写操作仍由 Service 进行 ownership、状态、版本、冲突和幂等校验，HITL 不是唯一安全边界。

### 4.4 Memory 与 Context Engineering

Memory 数据流：业务写入产生 `ScheduleChange`，事务提交后 5 秒防抖触发 Celery 重建，统计最近 180 天事实并写入 LangGraph Store；`TimeMemoryMiddleware` 按请求意图排序候选，在默认 800 Token 预算内注入。

关键设计：

- 业务事实仍在 PostgreSQL；Store 中画像可删除、可重建、可迁移；
- 时间窗口按用户 IANA 本地自然日统计，跨天/重叠事件先做区间并集；
- 声明偏好与派生规律分离，低样本或未知 schema 不注入；
- Tool 数据统一加“不可信事实、不是指令”的标签，降低间接 Prompt Injection 风险；
- Briefing 不消费 Time Steward 私人画像，避免跨工作流的上下文越界。

证据：`backend/apps/time_memory/analyzer.py`、`ranking.py`、`prompt_renderer.py`、`middleware.py`、`docs/architecture/time-steward-memory.md`。

### 4.5 个体估时与容量

第一层：`TaskExecutionSignalService` 记录 started/paused/resumed/completed/skipped，不用 `completed_at - started_at` 伪造实际工时；`duration_evidence.py` 从信号区间计算 active minutes。  
第二层：`DecisionProfileService` 先使用显式 project/tag 分组，再用版本化中英 taxonomy 做确定性语义分类；分组至少 3 个执行样本才使用时间衰减中位倍率，否则回退全局/固定 baseline，并返回来源、样本、置信度、版本和 fallback reason。

`CapacityForecastService` 用工作时间、事件、计划任务和未计划工作量计算 available/committed/unplanned minutes、风险级别和 reason codes。前端只展示后端结果，不复制容量规则。

### 4.6 确定性 Planner v2

第一层：按 priority、due_at、created_at、id 稳定排序；基于工作时段、Event、已计划 Task、草案内占用、deadline、buffer、lock、splittable/minimum chunk 构造可行位置。  
第二层：不能安排的任务不会抛弃，而是以 `unplaced + reason_codes` 保存；`SchedulePlan` 记录 constraints、Decision Profile snapshot、evidence、TTL 和版本。应用时在同用户写锁和事务内重载事实、检查任务版本与所有冲突。

当前算法是可解释的 deterministic heuristic，不是数学意义的全局最优求解器。`compare` 提供 priority/deadline 与 longest-first 两种方案，`regenerate` 只重生成选中块以降低计划震荡。

### 4.7 主动洞察与晚报

第一层：确定性 Detector 扫描未来 48 小时截止/逾期任务和未来两天容量风险，生成带 evidence、severity、dedup key、expiry 的 `TemporalInsight`。  
第二层：`AttentionPolicy` 再根据总开关、IANA 安静时间、每日配额、同类冷却和用户禁用类型决定仅存储还是创建 `NotificationDelivery`；投递状态机不承担“是否值得打扰”的判断。

晚报由 `EveningBriefingService` 直接聚合当天事实、执行差异、未完成事项与次日容量，可通过 Celery 定时生成和通知；当前不是由独立“总结 Agent”自由发挥，真实模型编辑与真实渠道效果尚未验收。

### 4.8 受控局部重排

第一层：`detect_disruptions` 找出计划任务与新 Event 的真实重叠；`preview_local_replan` 只处理显式 movable task ID，返回 before/after、移动分钟、无法安排项和 reason code，不写数据库。  
第二层：Apply 要求对象级 `AutomationPolicy`、allowlist、move cap、版本与最新冲突重验；高风险 Agent Tool 仍走 HITL。成功写入前后快照到 `ScheduleChangeBatch`，可用版本保护的 API 撤销；故障注入测试覆盖事务整体回滚。

### 4.9 外部日历同步

Google Calendar 当前为只读：OAuth state 只保存哈希且一次性消费，Token 用独立 Fernet key 加密并支持轮换；CalendarList/Events 分页有界，sync token 410 时在指定窗口全量对账，删除事件用 tombstone，外部身份包含 provider/account/calendar/event。

Celery polling 按连接状态与 `next_sync_not_before` 选有界批次，临时/限流错误最多重试 3 次，认证/永久错误 fail closed。真实 Google 沙箱授权、撤权、429 和长期增量同步仍为 `NOT VERIFIED`；Microsoft、Webhook、外部写回未实现。

### 4.10 并发、一致性与异步执行

- Event 使用 `expected_version` 乐观锁；审批、计划和变更批次也有版本保护；
- 同一用户的日程类写操作在事务级统一串行化，避免不同入口各自锁表仍产生竞态；
- Reminder、Notification、执行信号和局部重排使用稳定幂等键；
- `transaction.on_commit` 后再投递 Memory/后台任务，避免事务回滚后消费不存在的事实；
- AgentRun、SSE Event 和 Tool audit 落 PostgreSQL，前端可用 cursor 重连；
- Celery 的重试只重试瞬时执行/投递失败，不重新做 LLM 决策。

## 5. 技术选型与 Trade-off

| 选择 | 为什么采用 | 替代方案 | 收益 | 代价 |
| --- | --- | --- | --- | --- |
| Django 模块化单体 | 业务表和跨域事务紧密，当前规模无需独立扩缩容 | FastAPI 微服务 | ORM、事务、Admin、DRF 契约完整，一致性简单 | 后台重任务需注意进程/队列隔离 |
| PostgreSQL 权威 + LangGraph Store 派生 Memory | 业务事实必须可审计，Memory 可重建 | 只用向量库/聊天历史 | 一致性、删除与重算明确 | 需要维护事实到画像的更新链路 |
| `create_agent()` + 轻量 Outer LangGraph | 框架负责标准 Agent loop，Graph 负责业务级持久路由 | 手写 ReAct loop；所有步骤都画成 Graph | 少重复、可用官方 Middleware/HITL | 框架升级和消息协议需要严格测试 |
| 确定性 Planner | 时间数学和冲突必须可复现 | LLM 直接排程；OR-Tools/CP-SAT | 可解释、快、便于 reason code | 当前 heuristic 不保证全局最优 |
| Celery Beat/Worker | 提醒和定时工作需要可靠、可重试、与 Web 解耦 | APScheduler；云任务；LLM 定时 | 确定性、成熟、可审计 | Redis/Celery 运维和重复执行设计成本 |
| SSE | Agent 主要是服务端单向增量事件 | WebSocket、轮询 | HTTP 语义简单，适合流式文本和游标恢复 | 反代超时、连接清理和断线恢复需专门处理 |
| Provider Protocol | 天气/新闻/日历/通知可能替换 | 业务代码直接依赖 SDK | Mock、降级和扩展边界清楚 | 需要维护 DTO/错误语义，不能制造空抽象 |
| Session + Native Token 双通道 | Web 同源 Session 成熟，Capacitor 不能依赖 Cookie/CSRF | 全部 JWT/OAuth | 两端各用合适安全模型 | API Client 和测试需覆盖互斥分支 |
| Capacitor 复用 React | 团队可复用 Web UI，少维护一套业务页面 | 原生 Android/Flutter | 功能上线快、规则不复制 | 原生交互、后台能力与安装兼容需 Plugin 补齐 |
| 自托管 APK 更新 | 当前无应用商店发布链路 | Google Play In-App Updates | 可控、可直接发布 | 签名保管、OEM 安装器兼容和人工验收责任更大 |

## 6. 关键技术难点与真实问题

### 6.1 相对时间在异步/多轮 Agent 中漂移

- **现象**：模型处理“明天/两天后”时可能依赖执行时系统时间；排队、重试或多轮会话会让同一请求出现不同绝对时间。
- **定位**：检查 `RuntimeContext.current_datetime`、Tool 参数和多轮 eval，发现必须区分运行锚点与实时观测时钟。
- **根因**：相对时间含义依赖一个未显式固定的时钟；模型和 Worker 的隐式 now 不可靠。
- **方案**：Trigger 创建不可变 run anchor；Tool 返回 anchor 与 observed time；时间解析只用 anchor + IANA timezone；新增多轮 fresh-anchor eval。
- **结果**：提交 `779435d` 固化实现，13 个固定 Agent 场景中包含 1 个双轮相对时间回归案例；真实模型跨 Provider 结果仍需持续发布评测。

### 6.2 HITL 审批与后台 Worker 的竞态

- **现象**：批准请求与 Worker 接管之间可能重复恢复，或 Proposal 已决定但 AgentRun 状态仍不一致。
- **定位**：围绕 Proposal version、状态转换、Celery 接管与 checkpoint 恢复检查并发路径。
- **根因**：审批决定和恢复执行是两个阶段；仅靠前端禁用按钮不能保证 exactly-once。
- **方案**：Service 内 `select_for_update`、expected version、幂等决定；先落审批事实并把 run 转为可接管状态，再用 `Command(resume)` 恢复；过期统一作为 reject，不自动批准。
- **结果**：approve/edit/reject/expire/失败 Tool 均有测试和审计，未经批准不产生对应业务写入。

### 6.3 PostgreSQL SSE 连接被错误清理

- **现象**：SQLite 回归通过，但独立 PostgreSQL 17 全量测试中，SSE 轮询在事务内留下 psycopg `BAD` connection。
- **定位**：在全新 PostgreSQL 容器执行 migrations、LangGraph setup 与全套 pytest，定位到事务中的无条件连接清理。
- **根因**：流式轮询路径没有区分事务内与非事务连接，清理时破坏了当前事务连接状态。
- **方案**：仅清理非事务连接，并增加 PostgreSQL 全量回归与真实后端 E2E。
- **结果**：SQLite 与 PostgreSQL 17 均达到 `474 passed, 3 skipped` 的记录；该结果不代表并发上限或长期连接稳定性。

### 6.4 洞察通知幂等键与不可变事实冲突

- **现象**：生产升级扫描中，旧 deep-link payload、变化的剩余小时正文与重新计算的 decision time 复用了同一幂等键，被 Notification Service 拒绝。
- **定位**：对比洞察 dedup、AttentionDecision 与已物化 `NotificationDelivery` 的 payload。
- **根因**：幂等键表示“同一次投递”，但生成输入含随时间变化字段；相同 key 对应了不同业务内容。
- **方案**：保留首次检测/未变化 decision anchor；版本化 key；按 insight source/channel 将已创建 Delivery 视为不可变投递事实。
- **结果**：升级兼容与重复扫描回归已覆盖，真实通知观察窗口仍需补测。

### 6.5 Android 安装器显示旧版本

- **现象**：App 显示 1.1.6 可下载，但系统安装界面仍显示 1.1.5。
- **定位**：核对本地与公网 APK 的 manifest、size、SHA-256 和 signer，均确认是 1.1.6；旧更新器每次都使用同一 FileProvider URI。
- **根因**：最符合证据的解释是 OEM 安装器按固定 content URI 缓存旧包元数据；由于无设备日志，这一点仍是推断。
- **方案**：1.1.7 使用 `versionCode + hash prefix` 唯一文件名，清理旧文件、禁用 HTTP cache，并新增 versionName 校验。
- **结果**：1.1.7/11 已构建、签名、zipalign、发布并公网回下载校验；真机升级链路仍为 `NOT VERIFIED`。

### 6.6 Planner 的“可行”与“看似最优”

- **现象**：旧 first-fit 会让短任务占用唯一长槽，容量不足时也难以解释未安排原因。
- **定位**：构造固定“长短槽错配”反例并比较算法输出。
- **根因**：按输入顺序贪心只保证局部可放置，不考虑槽位稀缺性；失败被异常吞掉，缺少结构化解释。
- **方案**：稳定排序、硬约束 gate、placed/unplaced、reason codes、方案比较、应用前重验，并保留 benchmark baseline。
- **结果**：固定 4 case/11 task 中 baseline 安排 7 项、候选安排 8 项，硬约束违反均为 0；只证明该合成反例，不能写成真实用户规划提升。

## 7. Agent 特有能力审查

| 能力 | 状态 | 实现方式与边界 |
| --- | --- | --- |
| Planning | 已实现，受限 | Agent 调用确定性规划 Service 生成/比较/验证/锁定/放弃草案；不让模型计算时间或宣称全局最优 |
| Routing | 已实现 | `route_trigger` + Outer Graph 区分 user message、reminder、briefing、calendar sync、resume 等触发 |
| Tool Use | 已实现 | 40 个注册 Tool；动态暴露、Schema 校验、Service 边界、调用审计 |
| Context | 已实现 | RuntimeContext 注入 actor、timezone、locale、request/run ID 和显式时间锚点 |
| Short-term Memory | 已实现 | PostgreSQL Checkpointer 保存 thread/messages/interrupt，可跨进程恢复 |
| Long-term Memory | 已实现 | PostgreSQL 事实 -> 统计画像 -> LangGraph Store -> 按意图和 Token 预算注入；可关闭/清空/排除 |
| Reflection | 未实现为独立 Agent | 没有 Critic/Reflection loop；Briefing 只有一次有限结构修复，Planner 用确定性 validate/regenerate |
| Retry | 已实现，有上限 | Model/Tool 各默认重试 2 次；Provider/通知/Celery 有独立有限重试 |
| Fallback | 已实现 | 可配置备用模型；Briefing 可结构化 fallback；策略/外部数据失败时 fail closed 或部分降级 |
| Workflow | 已实现 | Outer LangGraph、Briefing workflow、HITL resume、Celery deterministic workflows |
| Handoff | 已实现 | `transfer_to_briefing` 使用 `Command.PARENT`，保持合法 ToolMessage 序列 |
| HITL | 已实现 | ActionProposal + HumanInTheLoopMiddleware + interrupt/resume + TTL |
| Harness | 已实现基础 | Runtime builder、配置校验、Tool audit、SSE protocol、管理命令、固定 fixtures |
| Evaluation | 已实现基础 | 真实模型 trajectory eval、规划/Memory/自适应 benchmark、洞察 guardrail、测试与观测；真实数据不足 |
| Multi-Agent | 明确未实现 | 仅 Time Steward 与短生命周期 Briefing Agent，不是自治 Agent 网络 |
| RAG | 未实现 | 无向量库、Embedding 或文档检索，不应包装成 RAG 亮点 |

### Phase A-E 中 Agent 具体做了什么

- **Phase A**：查询任务执行摘要和脱敏的外部日历同步状态；不推断未记录行为，不负责日历轮询。
- **Phase B**：`recommend_task_duration`、`get_capacity_forecast`、`record_task_duration_feedback` 已接入；Agent 解释结构化建议并记录用户显式反馈，不能从自由文本 Memory 生成硬规则。
- **Phase C**：生成/比较计划草案、检测扰动、验证、锁定计划项、放弃草案，并通过 HITL 应用计划；冲突与排程由 Service 计算。
- **Phase D**：列出、读取和处置 Temporal Insight；只有用户主动进入对话后才使用 Agent，定时扫描/晚报不先调用 Time Steward。
- **Phase E**：读取 Automation Policy、检测真实日程扰动，并通过高风险 `apply_local_replan` Tool + HITL 执行受控局部重排；自动 Dispatcher 是确定性 Celery，不是 Agent 自主循环。

## 8. 评测体系

### 8.1 自动化测试层次

- 后端：pytest-django，当前 78 个测试文件、源码中 459 个 `test_` 函数；最近完整记录为 SQLite 和 PostgreSQL 17 各 `474 passed, 3 skipped`。
- 前端：Vitest/RTL 当前记录为 26 个文件、107 passed；源码当前有 30 个测试/Spec 文件、122 个 `it/test` 声明，数量差异来自 E2E 与后续新增文件，不能直接等同于最近一次通过数。
- E2E：fixture Playwright 记录 `27 passed, 1 skipped`；隔离真实后端 Phase A-E 链路 `1 passed`，且不注册 API route mock。
- 契约：drf-spectacular 生成 `backend/openapi.json`，openapi-typescript 生成前端类型；API 变更必须成对提交。
- 数据库：除默认 SQLite 外，用全新 PostgreSQL 17 运行 migration、LangGraph setup 和全量测试，避免只在测试替身上成立。

### 8.2 Agent 回归与真实模型 Eval

`backend/tests/fixtures/time_steward_eval.json` 当前有 13 个场景、14 个 turn，覆盖创建提醒、查询今日安排、创建会议/任务、只读空闲时间、模糊请求不写入、跨用户拒绝、Prompt/凭据/Memory 外泄和多轮时间锚点。`evaluate_time_steward` 调用真实模型，检查 required/allowed/forbidden tools、响应禁用模式、错误与延迟。

局限：固定集规模小，尚未系统覆盖 Phase B-E 的计划失效、Memory 冲突、Provider stale、洞察误报和局部重排 trajectory；没有可引用的真实模型通过率、Token p50/p95 或 Provider 横向结果。

### 8.3 已有 Benchmark

| Benchmark | Baseline | Metric | 当前证据 |
| --- | --- | --- | --- |
| `benchmark_planning` | first-fit vs longest-first best-fit candidate | placed tasks/minutes、placement ratio、hard violations | 固定 4 case、11 task：7 vs 8 项，390 vs 480 分钟，0 hard violations；仅合成回归 |
| `benchmark_adaptive_planning` | bounded local repair vs full compaction | moved count、total/max movement、deadline/overlap violations | 固定 1 case：1 项/60 分钟 vs 3 项/480 分钟，均 0 violation；仅合成回归 |
| `benchmark_time_memory` | fixed 30m、user estimate、global calibration、stratified | 时序留出 MAE、confidence calibration error、bins、fallback count | 命令与输出已实现；真实用户不足 10 个完整样本，`需要补测` |
| `evaluate_insight_guardrails` | 调用方预声明阈值 | action/dismiss/failure/false-positive rate | 计算链已实现；无真实观察窗口，`需要补测` |

### 8.4 Trace 与 Metrics

- `AgentRun`、`AgentEvent`、`ToolCallAudit`、`ActionProposal`、`BriefingRun`、`NotificationDelivery` 提供业务轨迹；
- `LLMCallAudit` 保存 component/model/status、Token、Memory Token/ratio、duration 和 error type，不保存私有推理或原始敏感 Prompt；
- Prometheus 暴露 Agent run 状态/耗时 p50/p95、Tool 调用、Briefing、Notification、Proposal、LLM 调用与 Token；标签保持低基数，不含 user/request ID；
- `X-Request-ID` 关联浏览器、Nginx 和 Django JSON 日志；Loki/Alloy 用于日志查询。

## 9. 量化数据

### 9.1 可以引用，但必须带限定条件

| 数据 | 数值 | 限定与证据 |
| --- | ---: | --- |
| Time Steward 注册 Tool | 40 | `backend/apps/agents/tools/__init__.py` 各分组实际合计；不是 45 个 decorator 数 |
| Briefing 只读 research Tool | 5 | calendar/task/weather/news/source catalog，`briefings/tools.py` |
| Agent 固定 Eval | 13 cases / 14 turns | `backend/tests/fixtures/time_steward_eval.json` |
| Agent 配置上限 | model 8、tool 16、recursion 50、concurrency 4 | 默认配置，不是吞吐实测 |
| 最近后端全量测试 | 474 passed / 3 skipped | SQLite 与一次性 PostgreSQL 17；记录于战略文档 2026-08-24 |
| 最近前端单测 | 26 files / 107 passed | 2026-08-24 本机记录 |
| 最近 fixture E2E | 27 passed / 1 skipped | 2026-08-24 本机记录 |
| 真实后端 E2E | 1 passed | 隔离 PostgreSQL/Redis/Uvicorn/Vite，不是生产流量 |
| 规划合成集 | 4 cases / 11 tasks | baseline 7 项 vs candidate 8 项，只能解释合成反例 |
| 局部重排合成集 | 1 case | 1 项/60m vs 3 项/480m，只能说明 benchmark 可运行 |
| Android release | 1.1.7 / code 11 / 4,165,146 bytes | SHA-256、签名、zipalign、公网回下载已核验；真机未验收 |
| 默认审批 TTL | 24 h | `ACTION_PROPOSAL_TTL_SECONDS` 默认值，配置值不是业务效果 |
| Memory 窗口/预算 | 7/30/180 days，800 tokens | 算法/配置参数，不是效果数据 |

### 9.2 严禁写入简历的未验证数据

- 真实用户数、DAU、留存、使用频次：**需要生产统计**；
- 并发用户数、QPS、p95 API/SSE/Agent latency：**需要负载测试**；
- Agent Tool 选择准确率、端到端成功率、Token/成本下降：**需要固定模型评测报告**；
- 个体化估时相对 baseline 的 MAE 改善：**需要至少达到真实样本门槛并做时序留出**；
- 规划器真实任务完成可行性、碎片化改善：**需要脱敏真实计划集**；
- 洞察 precision/recall、行动率、误报率和通知疲劳：**需要标注集与线上观察窗口**；
- Google Calendar 同步规模、延迟、稳定性：**需要沙箱/真实 Provider 报告**；
- Android 安装成功率与通知动作可靠性：**需要多版本真机证据**；
- CPU、内存、数据库连接和队列延迟：**需要稳定运行和压测数据**。

## 10. 工程化能力

### 10.1 部署与服务

- Compose 服务包含 PostgreSQL 17、Redis 7 AOF、Django/Uvicorn ASGI、Celery Worker、Celery Beat、前端 Nginx 和入口 Nginx；
- production overlay 强制 production settings、安全 Cookie，并将入口绑定到 loopback，公网 TLS 交给 Cloudflare Tunnel/外部代理；
- Nginx 对 SSE 关闭 buffering/cache，读写超时 3600 秒；运行时解析容器 DNS，避免 Django 重建后保留旧 IP；
- APK 只允许严格文件名路径并设置下载响应头；OAuth callback 关闭 access log，避免 query 中 code/state 进入 Nginx 日志。

### 10.2 可靠性

- health live/ready 区分进程存活与 PostgreSQL/Redis 就绪；Compose 依赖健康检查与 restart policy；
- Reminder/Notification 有状态机、claim、幂等、有限重试和审计；
- ActionProposal 有 TTL、版本、行锁和安全拒绝；
- PostgreSQL custom-format 备份与显式确认恢复脚本已提供；实际隔离恢复演练仍需完成；
- APK 校验 package/version/hash/signature，签名 lineage 作为兼容性关键资产记录。

### 10.3 可观测性

可选 overlay 包含 Prometheus 3.5、Grafana 12.1、Alertmanager 0.32、Loki 3.5、Alloy 1.10 及 PostgreSQL/Redis/Celery exporter；默认仅本机访问，公网 `/metrics` 返回 404。日志驱动开启 10 MB × 3 轮转。

当前已具备配置和本地验证基础，但真实告警邮件送达、长时间 dashboard 数据、容量阈值和 SLO 尚未验收。

### 10.4 安全与权限

- Web 使用 Session + CSRF，Android 使用 DRF Token 且不带 Cookie；Token 登录会轮换旧 Token；
- 所有查询按当前 actor 隔离，高风险操作有 HITL；游客账户有过期、配额和能力禁用；
- Google OAuth state 一次性、Token 独立加密/轮换，callback 日志脱敏；
- Tool/外部数据标记为 untrusted，评测覆盖系统提示词、凭据和跨用户数据外泄；
- 不记录 API Key、Cookie、请求正文、原始用户对话或模型私有推理。

## 11. 项目不足与进一步优化

1. **缺少真实价值证据**：工程闭环多，但用户行为、估时提升、计划质量与通知价值都缺真实数据。下一步优先采集匿名化执行和反馈，不继续堆 Tool。
2. **Planner 仍是 heuristic**：可解释但不保证全局最优。应先用真实 benchmark 证明问题，再评估 OR-Tools CP-SAT、加权区间调度或局部搜索。
3. **Agent Eval 覆盖落后于 Phase B-E**：需扩充固定 trajectory、越权/失效/fallback 场景，并保存模型版本、Token、延迟和成本。
4. **外部日历事实仍不完整**：Google 尚未真沙箱验收，Microsoft/Webhook 未做，ICS 私有 URL 仍为明文连接标识；应优先补 Provider 安全和同步新鲜度。
5. **主动能力缺线上 guardrail**：策略代码存在，但真实渠道 action/dismiss/false-positive 窗口未跑，不能证明“克制”。
6. **Android 运行证据不足**：构建和下载链成立，真机上的升级、后台、离线动作和 OEM 差异仍需验证。
7. **Phase 10 尚未完成**：完整观测栈、告警送达、恢复演练、基础负载和真实模型发布评测仍是外部/运行验收项。
8. **当前工作区改动过大且未提交**：Phase A-E 与 1.1.7 横跨大量文件；应按领域拆分提交/PR，补变更说明，降低回滚和归属风险。
9. **旧规范存在阶段口径差异**：`PROJECT_SPEC.md` 仍带“架构设计/MVP 准备”表述，README/战略文档更接近当前事实；后续应更新规范版本但不能覆盖 ADR。
10. **没有 RAG 也不需要急于添加**：当前产品瓶颈是时间事实、评测和 Provider，不是文档召回；只有出现真实知识检索场景再引入向量能力。

## 12. 面试深挖问题（25 题）

1. 为什么 Time Steward 必须用 `create_agent()`，外层 LangGraph 又为什么仍然存在？
2. 为什么不把 Agent 的每一次思考和 Tool 调用都画成 LangGraph 节点？
3. PostgreSQL、LangGraph Checkpointer、LangGraph Store、Conversation 分别保存什么？为什么不能合并？
4. 一条“明天下午三点创建会议”的请求，时间锚点如何确定？排队两分钟后执行会不会漂移？
5. DST 不存在时间和歧义时间如何处理？为什么只存 UTC 还不够？
6. 40 个 Tool 会不会让模型选择困难？为什么把多个 Event 写操作收敛到 `mutate_events`？
7. Tool 为什么不能直接调用 ORM？Service 层除了代码整洁还解决了哪些一致性问题？
8. 哪些操作需要 HITL？为什么不能只在前端弹确认框？
9. ActionProposal 批准接口重复提交、Proposal 过期、Worker 重复接管时如何保证不重复执行？
10. `Command(resume)` 为什么必须恢复同一 thread？换一个新 AgentRun 会丢失什么？
11. Reminder 为什么绝不能经过 LLM？Celery Beat 重启和重复扫描时如何避免重复通知？
12. SSE 为什么优于 WebSocket？断线续传、代理缓冲、长连接数据库清理分别怎么做？
13. PostgreSQL 回归发现 psycopg `BAD` connection 的过程是什么？为什么 SQLite 没发现？
14. Time Memory 为什么不是 RAG？它如何做时间窗口、排序、Token budget 和用户删除？
15. 如何防止恶意日程标题或 RSS 内容对 Agent 做间接 Prompt Injection？关键词检测为什么不能作为安全边界？
16. 实际工时为什么不能用完成时间减开始时间？暂停/恢复信号如何计算 active minutes？
17. 个体估时为什么使用时序留出而不是随机切分？冷启动和小样本怎样回退？
18. Decision Profile 的置信度为什么只能作为 Planner 软约束？阈值 5 样本、0.6 置信度如何进一步验证？
19. Planner v2 为什么没有直接用 OR-Tools？当前 heuristic 的最坏情况是什么？
20. 什么是“未安排原因准确率”？如何证明 reason code 和真实不可行原因一致？
21. 计划草案为什么要持久化 constraints snapshot、TTL 和 task version？Apply 前为什么还要全量重验？
22. TemporalInsight、AttentionPolicy、NotificationDelivery 为什么要拆成三层？
23. 洞察通知复用幂等键为什么会失败？如何定义“同一次业务操作”的稳定 identity？
24. 局部重排相对全量压缩的目标是什么？如何度量计划震荡、稳定性和撤销质量？
25. 当前有哪些数字可以写进简历，哪些不可以？你会设计哪四组 benchmark 证明系统真的更好？

## 13. 最终提炼

### 13.1 最有竞争力的 5 个技术亮点

1. **可信 Agent 写入架构**：`create_agent + RuntimeContext + Tool Policy + Service + HITL + Audit`，将自然语言操作接入真实事务系统而不放弃权限和一致性。
2. **确定性时间与可恢复执行**：显式 run anchor、UTC/IANA/DST、PostgreSQL Checkpointer、SSE cursor 和 interrupt/resume 共同保证异步 Agent 的时间语义和运行恢复。
3. **从执行事实到个体决策**：不可变执行信号、时间衰减估时、置信度/fallback、容量预测和 Planner 软输入形成可评测的个人时间智能链路。
4. **可解释、可审阅、可撤销的规划系统**：机器可读未安排原因、计划快照/版本/TTL、应用前重验、Automation Policy、局部重排与撤销批次。
5. **AI 与可靠后台解耦**：提醒、洞察、Attention、通知和定时简报由 Celery/状态机确定性执行，模型仅做语义、Tool 路由和有限编辑。

### 13.2 最值得写进简历的 5 个成果

以下是“有证据的成果表达方向”，不是最终简历句子：

1. 设计并落地 Time Steward Agent，实际注册 40 个业务 Tool，通过 Application Service、动态风险策略和 HITL 审批接入日程/任务/提醒/规划等真实数据。
2. 建立 PostgreSQL 持久化的 AgentRun/Tool Audit/ActionProposal 与 SSE 断线恢复链路，覆盖审批、过期、取消、失败和进程恢复场景。
3. 实现确定性 Planner v2 与受控局部重排，在固定 4 case/11 task 合成集上保持 0 硬约束违反，并保留 baseline、未安排原因与应用前重验；不得外推为真实收益。
4. 构建任务执行信号、Decision Profile、容量风险和反馈闭环，支持按时间留出评测 MAE 与置信度校准；真实效果数据待采集。
5. 完成 Compose/ASGI/Celery/Nginx/Prometheus/Loki 与 Web/Capacitor Android 发布链路；1.1.7 APK 已通过 manifest/hash/signature/zipalign/公网回下载验证，真机验收待补。

### 13.3 最值得面试重点讲的 3 个技术难点

1. **相对时间确定性**：从隐式 now 问题，到 run anchor、IANA 时区、异步执行和多轮 fresh anchor 的完整设计。
2. **HITL 的 exactly-once 语义**：ActionProposal、行锁、版本、幂等决定、LangGraph checkpoint 和 Worker 恢复如何协作。
3. **规划的可信性与稳定性**：硬/软约束分离、不可行原因、草案快照、应用前重验，以及局部重排/撤销如何限制 Agent 自治。

### 13.4 当前缺少的量化实验与建议 Benchmark

1. **Agent Regression**：扩到至少覆盖 Phase B-E 的固定数据集；同一数据集比较主/备用模型，报告 Tool 选择与参数正确率、越权率、无依据断言率、重试/fallback、Token、成本、p50/p95。
2. **Duration Calibration**：收集真实执行样本，严格时间切分，比较 fixed-30、用户原估时、全局中位、用户历史、显式/语义分组；报告 MAE、Median AE、过短率、分桶校准误差和冷启动覆盖。
3. **Planning Quality**：脱敏真实周计划 + 合成边界集，对比 first-fit、EDF、priority-first、当前 v2 和可选 CP-SAT；先 gate 硬约束，再看加权按期可行性、placement、碎片、上下文切换、移动距离和 p95 延迟。
4. **Insight/Attention**：建立标注场景计算 detector precision/recall、dedup、expiry、actionability；线上预声明 guardrail，观察 action/dismiss/false-positive、重复通知和权限关闭率。
5. **Reliability/Load**：对 API、SSE、Celery reminder/notification、Agent 并发分开压测，记录 QPS、p50/p95/p99、数据库连接、Redis/Celery queue lag、CPU/内存和错误率。
6. **External/Device Matrix**：Google OAuth 首次/增量/410/429/撤权；Android 24、27 和主流系统测试升级、进程被杀、重复点击、离线重放和 OEM 安装器行为。

## 14. 证据索引

- 项目定位与规则：`README.md`、`PROJECT_SPEC.md`、`AGENTS.md`、`CLAUDE.md`
- 战略与 Phase A-E 状态：`docs/product/ai-native-time-agent-strategy.md`
- Feature Contract：`docs/product/feature-contracts-phase-a-e.md`
- Agent：`backend/apps/agents/agents/time_steward.py`、`outer_graph.py`、`middleware.py`、`tools/`
- HITL：`backend/apps/action_proposals/`、`docs/architecture/phase-6-action-proposal-hitl.md`
- Briefing：`backend/apps/briefings/agent.py`、`workflow.py`、`evening.py`、`tasks.py`
- Planning/Adaptive：`backend/apps/planning/services.py`、`adaptive.py`、`automation.py`、`benchmark.py`
- Memory/Decision：`backend/apps/time_memory/`、`docs/architecture/time-steward-memory.md`
- Insight/Attention：`backend/apps/insights/`
- External Calendar：`backend/apps/integrations/`、ADR 0023/0030
- Notifications：`backend/apps/notifications/`、`backend/apps/reminders/dispatcher.py`
- Contract/Test：`backend/openapi.json`、`frontend/src/api/generated/schema.d.ts`、`backend/tests/`、`frontend/tests/`
- Operations：`docker-compose*.yml`、`infra/`、`docs/operations/observability-and-evaluation.md`
- Android：`frontend/android/`、`frontend/src/native/`、`docs/android-build-and-verify.md`
- Git 关键节点：`dd0bd49`（Time Steward）、`7e1f7db`（HITL）、`f3b2b8b`/`d8faf55`（Briefing）、`04dfd50`（Notification）、`779435d`（相对时间确定性）

## 15. 可直接用于简历的项目经历版本

### Time Agent｜个性化时间管理智能体｜核心开发 / Agent Engineering｜2026.07 - 至今

面向个人日程与任务管理场景，解决通用聊天模型难以基于真实时间事实持续规划、可靠执行和主动跟进的问题，构建从自然语言决策到跨端执行的个人时间管理 Agent。

**技术栈：** Python、Django、LangChain、LangGraph、PostgreSQL、Redis、Celery、React/Vite、Docker、Capacitor Android

- **智能日程规划与执行：** 针对自然语言请求难以直接转化为可靠时间操作的问题，基于 LangChain Agent 与外层 LangGraph 编排日程、任务、提醒和计划的多步决策，并以约束校验、幂等、失败恢复及 HITL 审批保障真实写入可控；规划合成 Benchmark 覆盖 `4` 个场景、`11` 个任务，安排率由 `63.64%` 提升至 `72.73%`，硬约束违反数保持为 `0`。
- **长期个性化能力：** 针对通用建议缺少个人依据的问题，从真实安排与执行反馈中形成 `7/30/180` 天时间画像，通过增量更新、衰减排序和预算化注入驱动个体估时、容量判断与计划推荐，并支持用户纠正和遗忘。
- **主动时间管理服务：** 针对被动问答无法提前暴露风险的问题，将系统扩展到晚报、未来 `48` 小时截止风险和未来 `2` 天容量洞察，并打通后端事件触发、通知配额/安静时间与 Android 系统级调度，使风险在仍可调整时主动触达用户。
- **评测与持续优化：** 针对模型与 Prompt 迭代容易产生行为回退的问题，建立固定任务集、工具轨迹校验和可复现消融机制；真实 DeepSeek 评测覆盖 `13` 个场景、`14` 轮交互，Task Success 为 `92.31%`、Required Tool Recall 为 `95.83%`、Allowed Tool Precision 与时间约束满足率均为 `100%`、禁用工具调用为 `0`，Token/Task 为 `18,367`，p95 Latency 为 `8.02s`。

> 评测口径：2026-08-25 在当前工作树、Docker Compose 生产依赖拓扑和 `deepseek-v4-flash` 上单次运行；结果不是线上用户收益。唯一失败场景为“今日日程”漏查任务列表。旧时间上下文中间件的 `6` 场景真实模型消融中，完整组和移除组 Task Success 均为 `100%`，未观察到质量提升，因此不将其表述为模块收益；详见 `docs/operations/evaluation-results-2026-08-25.md`。

### 不应采用的表述

- 不写“基于 LangGraph 实现完整 Agent 内部推理流程”：内部循环实际由 LangChain `create_agent()` 提供。
- 不写“构建 RAG/向量数据库”：项目没有 Embedding、向量检索或通用文档 RAG。
- 不写“Agent 自动执行所有主动任务”：提醒、洞察扫描和调度由确定性 Celery/Service 执行，高风险动作需要 HITL 或显式 Automation Policy。
- 不把单次离线评测写成线上用户收益，不把旧时间上下文消融写成质量提升，也不写未经运行验证的个体估时提升或真实并发数字。
- Android 可以写成跨端工程能力，但在真机矩阵完成前，不写“保证进程退出后所有机型均可靠触发”或安装成功率。
