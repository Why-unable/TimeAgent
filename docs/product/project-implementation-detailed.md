# Time Agent 项目实现超详细版

> 更新日期：2026-08-29。本文是代码事实审计稿，不是产品宣传稿或简历。结论按以下状态标记：
> **已实现**（代码和测试存在）、**已配置未启用**（配置/接口存在但当前运行路径没有打开）、**仅接口/抽象**、
> **测试覆盖未生产验证**、**规划中/未实现**、**需要补测**。除非特别说明，所有路径均相对于仓库根目录。

## 证据和口径

- 首要规则：`CLAUDE.md`、`AGENTS.md`、`README.md`；架构决策见 `docs/decisions/`，路线见 `ROADMAP.md` 和 `docs/product/ai-native-time-agent-strategy.md`。
- 当前工作区包含大量未提交的 Phase A-E/Phase 10 修改。Git 作者名为 `Why-unable`/`hugh`，邮箱相同；这能证明同一开发身份的提交轨迹，但不能替代团队贡献确认。
- 真实模型数据：2026-08-25 使用 `deepseek-v4-flash`、Docker Compose 生产依赖拓扑运行；主集 13 场景/14 轮，Task Success `12/13=92.31%`，Required Tool Recall `95.83%`，Allowed Tool Precision 和时间约束满足率 `100%`，p95 `8.02s`，Token/Task `18,367`。这是一次小规模离线运行，不是线上用户效果。
- 旧时间上下文 6 场景消融中完整组和移除组均为 `100%`，未证明中间件带来增益；记录见 `docs/operations/evaluation-results-2026-08-25.md`。

## 一、项目定义与背景

### 1.1 场景、用户和问题

Time Agent 面向需要同时管理会议、任务、截止时间、提醒和个人节奏的知识工作者、学生与自由职业者。它要解决的不是“缺一个待办列表”，而是：

1. 日历、任务、提醒和外部日历分别记录事实，用户无法快速知道完整的时间承诺。
2. “有空”不等于“能完成”：任务时长、截止日期、工作时段、已占用时间和计划/实际差异没有被统一判断。
3. 计划被会议、延误或新任务打破后，手工重排的成本高，风险经常到截止前才暴露。
4. 通用 Chatbot 能理解文字，但不能把用户身份、当前时间、权限、版本和写入幂等当成可靠业务约束。

证据：`PROJECT_SPEC.md`、`README.md`、`docs/product/ai-native-time-agent-strategy.md` 第 1、3、4 节，核心模型 `backend/apps/events/models.py`、`tasks/models.py`、`reminders/models.py`。

### 1.2 为什么需要 Agent

固定 Workflow 足以完成“列出今天日程”或“到期提醒投递”，但无法覆盖“帮我把这些任务安排到下周、避开已有会议、解释放不下的原因”这类开放请求。Agent 负责：

- 识别自然语言意图和缺失信息；
- 在多个只读/写 Tool 之间选择顺序；
- 根据 Tool Observation 继续查询、澄清或结束；
- 在简报、规划、洞察等确定性服务之上做有限的自然语言解释。

Agent **不**负责：时间数学、权限、冲突、状态机、审批、调度、通知配额和数据库事务。这些由 Service、Workflow、Celery 和 PostgreSQL 完成。因此产品形态是“自然语言交互层 + 可靠事务系统”，不是端到端 LLM 日历。

### 1.3 目标与非目标

**目标（已部分实现）**：统一管理日程/任务/提醒；自然语言查询与受控写入；长期时间画像；计划草案、容量和截止风险；每日简报/晚报；跨 Web/Android 触达；审批、审计、恢复和可观测。

**非目标（当前明确不做）**：向量数据库/通用文档 RAG；大规模多 Agent 网络；Microsoft Calendar、Webhook 和外部日历写回；删除或代表用户向外发送消息；没有授权的全自动重排；复杂 RBAC；以模型替代 PostgreSQL 业务事实。

### 1.4 上线、规模与使用边界

- Web 已在本机生产 Compose + Nginx/Cloudflare Tunnel 上部署；Android `1.1.7 / versionCode 11` APK 已完成文件、签名、zipalign、公网回下载验证。
- 仓库具备游客隔离空间、Session Web 认证和 Android Token 认证；“可公网访问”不等于有正式外部用户。
- 当前没有可证明的 DAU、留存、正式用户量、生产 QPS、并发上限、长期通知行动率或用户效率提升数据，均标记为**需要补测**。
- 代码与本地验证规模可引用：40 个实际注册 Time Steward Tool、固定 Agent Eval 13 cases/14 turns、规划合成集 4 cases/11 tasks；这些是工程/测试规模，不是业务规模。

### 1.5 开发者角色

从 Git 提交和工作区变更看，项目为个人主导的端到端工程：产品边界、Agent Runtime、Tool/Service 约束、HITL、Memory、Planner、主动能力、API/前端/Android、评测和生产部署均有改动。正式简历不应把上游 LangChain/LangGraph 默认能力写成个人原创；具体归属仍应以提交/PR 进一步固化。

### 1.6 面试口述版

> 我做的是一个面向个人知识工作者的 AI 时间管理系统。起点是日历、待办和提醒各自记录信息，用户仍要自己判断什么时候做、是否来得及，以及计划被打乱后怎么调整；通用聊天模型又不能直接承担时间和写入的一致性责任。系统把真实日程事实放在 PostgreSQL，由 Agent 负责理解自然语言、选择工具和解释结果，确定性服务负责冲突、容量、审批、通知和事务。我主要设计并实现了 Agent 与业务系统的边界、可恢复的审批执行、长期时间画像、确定性规划和主动简报/洞察链路，并完成了 Web、Android 和生产部署。目前能力已经上线可用，固定模型评测为 12/13 通过，但真实用户规模、留存和效率提升仍需补测。

## 二、整体系统架构

### 2.1 模块边界

| 层 | 当前实现 | 状态 |
|---|---|---|
| Client | React/Vite、TanStack Query、SSE；Capacitor Android | 已实现 |
| API/Auth | Django 5.2、DRF、Session+CSRF、Android Token、OpenAPI | 已实现 |
| Conversation | Conversation、AgentRun、ToolCallAudit、AgentEvent | 已实现 |
| Agent Runtime | LangChain `create_agent()` 的 Time Steward；外层 LangGraph | 已实现 |
| Workflow | Outer Graph、Briefing Workflow、Reminder Dispatcher、Calendar Sync | 已实现/部分 |
| Service/Domain | events/tasks/reminders/planning/time_memory/insights/notifications services | 已实现 |
| Data | PostgreSQL 17 业务事实；LangGraph Checkpointer/Store | 已实现 |
| Background | Celery Worker/Beat，Redis broker/result/backend 配置 | 已实现；Redis 用途需按配置区分 |
| External | Model、Weather、News、ICS/Google Calendar、Email/Web Push | Provider 接口；部分真实验证待补 |
| Operations | Uvicorn ASGI、Nginx、Docker Compose、Prometheus/Grafana/Loki/Alertmanager | 已配置；部分观测/告警待验收 |

### 2.2 数据流和调用链

```text
Web/Android Client
  -> DRF Route/View + Auth
  -> Conversation/AgentRun Service
  -> Celery execute_agent_run_task
  -> TriggerEnvelope + RuntimeContext
  -> OuterGraph route_trigger
  -> Time Steward create_agent()
  -> middleware: runtime prompt / memory / policy / limit / retry / audit
  -> Model chooses Tool
  -> Tool -> Application Service -> Domain/Repository -> PostgreSQL
  -> ToolMessage Observation -> next model turn
  -> AgentEvent/ToolAudit/AgentRun persistence
  -> SSE cursor -> Client
```

高风险路径在 Tool 与 Service 之间插入 `HumanInTheLoopMiddleware`：`interrupt` 创建 `ActionProposal`，用户 approve/edit/reject 后以 `Command(resume=...)` 恢复原 thread。

定时路径不经过 Time Steward：`Celery Beat -> deterministic dispatcher/Briefing Workflow -> NotificationService -> Provider`。Scheduled briefing 直接进入 Briefing Workflow；Reminder 永不调用 LLM。

### 2.3 一次用户请求内部发生什么

1. 前端通过 `frontend/src/api/client.ts` 带 Session+CSRF 或 Native Token，并附 `X-Request-ID`。
2. `conversations/views.py` 创建/复用 Conversation，创建带 `anchor_at`、`anchor_timezone`、trigger payload 的 AgentRun，然后投递 Celery。
3. Worker claim AgentRun；`execution.py` 读取偏好，构建 `TriggerEnvelope` 和不可变 `RuntimeContext`。
4. `OuterGraphRuntime` 校验 user/trigger/conversation 一致性，按 trigger 选择 persistent 或 stateless graph，并应用 recursion/max concurrency。
5. `create_agent()` 加载系统 Prompt、工具 Schema 和 middleware；模型只能看到当前 read/write policy 允许的 Tool。
6. 模型发出 Tool call，Tool 通过 `ToolRuntime` 获取 actor、时区、anchor 和 request ID，调用 Application Service；Service 做 ownership、状态、版本、冲突、幂等和事务。
7. 结果变成 `ToolMessage` 回到 Agent 上下文；Agent 继续查询/澄清/解释，直到达到完成或限制条件。
8. `AgentEvent` 增量写入数据库，前端 SSE 按 cursor 重放；最终 AIMessage 写回 AgentRun。审批则在第 6 步暂停，等待另一个恢复请求。

同步 HTTP 只负责创建 run/返回 run ID；真正的 Agent 执行是 Celery 长任务。Reminder/简报/同步也是后台任务。当前没有 WebSocket；SSE 是单向事件流，客户端断开后 AgentRun 继续执行，重连使用已持久化事件 cursor。

### 2.4 进程内与持久化状态

- 进程内：当前模型实例、Tool registry、请求对象、`RuntimeContext`、本次 `BriefingAgentState`。
- PostgreSQL：User/Conversation/AgentRun/AgentEvent/ToolCallAudit/ActionProposal、日程/任务/提醒/计划、执行信号、洞察、通知、外部连接和 LLMCallAudit。
- LangGraph PostgreSQL Checkpointer：持久 thread state、messages、interrupt；不是业务事实库。
- LangGraph Store：可重建长期 Time Memory；不是权威日程库。
- Redis/Celery：队列、任务结果/运行时协调（具体 broker/backend 以 Compose 配置为准），不能替代 PostgreSQL。

横向扩展上，Django、Celery Worker、Nginx 可增加实例；同一用户写操作依靠数据库事务锁/版本保护。SSE 依赖共享持久化事件。单进程限制包括当前模型实例、Provider 客户端和没有统一分布式 Agent scheduler；生产并发上限**需要补测**。

## 三、个人核心贡献

### 3.1 Agent Runtime 边界

- **问题**：模型可能绕过 actor、时间锚点、写入 Service 或权限策略。
- **决策**：规定 `Tool -> Application Service -> Domain/ORM`，用可信 `RuntimeContext` 传递身份/时间，用 dynamic Tool Policy 控制暴露集合。
- **实现**：`agents/time_steward.py` 调 `create_agent()`；`middleware.py` 注入 prompt、policy、limits、retry、audit；`tools/common.py` 做 actor/writable 检查。
- **验证/结果**：Agent tests、跨用户拒绝、只读模式、Tool 审计和固定 trajectory；真实并发隔离仍需补测。

### 3.2 可恢复 HITL 执行

- **问题**：创建/取消/批量排程等写操作有不可逆或高影响副作用。
- **决策**：前端确认不能作为安全边界，审批事实必须服务端持久化、幂等和可过期。
- **实现**：`HumanInTheLoopMiddleware` + `interrupt`；`ActionProposalService` 记录 proposal/version/TTL；approve/edit/reject 后 `Command(resume=...)` 回原 thread；Service 再次做版本/冲突/权限校验。
- **结果**：未经批准不落业务库，过期安全拒绝；多 Worker 抢占、恢复失败和真实生产压力仍需补测。

### 3.3 时间语义确定性

- **问题**：排队、重试和多轮对话让模型使用隐式系统时间，导致“明天/两天后”漂移。
- **决策**：每次 run 固化 `anchor_at`，Tool 相对时间必须使用 `time.kind=relative`，明确绝对时间才使用 absolute。
- **实现**：`RuntimeContext.current_datetime` 统一转 UTC；`TemporalContextMiddleware` 给历史消息加旧 anchor 标记并移除历史 clock Tool；`779435d` 固化相对时间行为。
- **结果**：多轮回归和真实消融已运行；6 场消融两组均满分，不能宣称该中间件单独提升质量。

### 3.4 从执行证据到个人决策

- **问题**：用户估时不等于实际投入，Memory 容易变成不可审计的自由文本画像。
- **决策**：只从明确 execution signals 计算 active minutes，低样本回退，不把推断当硬约束。
- **实现**：`TaskExecutionSignalService`、`duration_evidence.py`、`DecisionProfileService`、7/30/180 日窗口和 800 token 注入预算；反馈写入业务表，派生画像可重建/删除。
- **验证/结果**：单元和 benchmark 能运行；真实个体化 MAE、覆盖率和长期行为改善需要补测。

### 3.5 确定性 Planner 与局部重排

- **问题**：LLM 直接排程不可复现、难以解释，也容易产生冲突。
- **决策**：模型负责理解目标和展示方案，Service 负责时间计算；先输出草案，再确认应用。
- **实现**：`SchedulePlan` 记录 constraints/Decision Profile snapshot/TTL/version；Planner v2 生成 placed/unplaced/reason codes；apply 前重验；Adaptive Planning 限制 allowlist、move cap、Automation Policy，并用 `ScheduleChangeBatch` 支持撤销。
- **结果**：4 case/11 task 合成集中 baseline 安排 7 项、候选 8 项，390→480 分钟，零重叠；真实计划质量仍需补测。

### 3.6 主动服务与工程化

主动洞察由 `TemporalInsight` detector + `AttentionPolicy` + `NotificationDelivery` 构成；晚报由 `EveningBriefingService`/Briefing Workflow 生成；提醒由 Celery Dispatcher 投递。个人还实现了 SSE cursor、JSON/X-Request-ID、脱敏 LLM audit、OpenAPI/前端类型生成、Android 自更新和 Compose/Nginx 发布链路。告警送达、真实 Provider、Android 真机和生产负载仍需补测。

## 四、Agent 内部运行机制

### 4.1 State：实际字段与持久化

`AppState`（`backend/apps/agents/state.py`）继承 `AgentState`，实际字段为：`messages`（框架 channel，持久 graph checkpoint）、`trigger_type`、`trigger_payload`、`operation_id`、`active_workflow`、`workflow_result`、`remaining_steps`。没有 `user_id`/`thread_id`/`plan`/`todos` 字段；这些在 `RuntimeContext`、Runnable config metadata、业务表或 Tool 返回中传递。

`TimeStewardState` 仅增加 `time_memory_profile` 和带 `operator.or_` reducer 的 `schedule_changed`。Agent 的 Tool results 以框架消息进入 `messages`，不是自定义 `tool_results` 数组。`thread_id` 位于 checkpointer config；`user_id`、request ID、agent run ID 位于 RuntimeContext/metadata。

`BriefingAgentState`（`briefings/state.py`）有 `research_results`、`attempted_sections`、`repair_mode`，明确不 checkpoint；最终 evidence 复制到 `BriefingRun/SectionRun`。因此“Agent state 全部持久化”是不正确的。

### 4.2 Node、Edge 与 Loop

Outer Graph 的节点是 `time_steward_agent`、`briefing_workflow`、`calendar_sync_workflow` 等 workflow node；`route_trigger` 根据 `TRIGGER_ROUTES` 确定性选择目标。`reminder_due` 走 dispatcher，不经过 Agent；`user_message` 走 Time Steward；manual/scheduled briefing 走 Briefing；calendar webhook 走 sync workflow（当前 runtime 可使用 unavailable node，真实写回未实现）。

Time Steward 内部 node/edge 不是项目手写，而由 LangChain `create_agent()` 负责模型-Tool loop。模型决定是否发 Tool call、调用哪个允许的 Tool、是否继续；middleware 和 graph 负责限制、策略和外层路由。Briefing Workflow 的 section 循环、失败修复和聚合由代码控制，Briefing Agent 只做只读研究与结构化报告。

标准循环是：

```text
System/Runtime Context + messages
  -> Model reasoning (上游框架内部)
  -> AIMessage tool_calls
  -> ToolPolicy/HITL/Audit
  -> Tool -> Service -> DB/Provider
  -> ToolMessage observation
  -> create_agent 再次调用模型
```

### 4.3 Stop Condition

实际存在的停止机制：

- LangGraph `recursion_limit`，默认配置 `50`；超限转为 `GraphStepLimitExceededError`。
- ModelCallLimitMiddleware 默认单轮模型调用上限 `8`；ToolCallLimitMiddleware 默认 Tool 调用上限 `16`。
- Model/Tool retry 默认各 `2` 次；失败由 `ToolErrorMiddleware`/AgentRun fail 路径收束。
- LangChain `RemainingSteps` channel 协助框架结束；没有项目自定义的“模型说完成就无限继续”。
- Celery AgentRun soft limit `180s`、hard limit `195s`；stale run recovery 默认按 `AGENT_RUN_STALE_MINUTES` 处理。
- 用户取消：`AgentRunService` 检查取消状态，流式消费抛 `AgentRunCancelled`。
- HITL interrupt：等待 proposal 决定，不是成功结束；resume 或 reject 才继续/终止。

未发现独立的 loop detector、基于语义重复的循环检测、token budget stop（Memory 有 token budget，但不是全 Agent budget）或 deadline-aware Agent stop。它们是后续补强项。

## 五、Planning、Routing、Reflection 与 Workflow

| 能力 | 判断 | 证据/主链路/局限 |
|---|---|---|
| Planning | 已实现但主要是确定性 Planner | `apps/planning/` 生成草案；Agent 通过 Tool 调用，不是模型自由规划全部时间数学 |
| Plan-and-Execute | 部分 | 草案生成→验证→用户确认→应用；没有通用 planner/executor 两个 LLM Agent |
| ReAct | 框架内部存在 | `create_agent()` 的模型-Tool 循环具备 action/observation；项目没有手写 ReAct |
| Router | 已实现 | `route_trigger` + `TRIGGER_ROUTES`，确定性按 trigger 路由 |
| Supervisor | 未实现 | 没有 supervisor 管理多 Worker Agent |
| Handoff | 已实现 | `transfer_to_briefing` 通过 `Command.PARENT` 交给 Briefing workflow |
| Reflection | 未实现为独立能力 | 无 Critic loop；Briefing 仅有有限结构修复，Planner 由 `validate/regenerate` 确定性处理 |
| Evaluator-Optimizer | 未实现 | 有离线评测和 benchmark，但不是在线生成-评审-优化闭环 |
| HITL | 已实现 | ActionProposal + interrupt/resume；高风险写入主链路 |
| Retry/Fallback | 已实现有界 | middleware、Celery、Provider 分层；不是无限重试或熔断 |
| Workflow | 已实现 | Outer Graph、Briefing、Reminder、Calendar sync |
| Harness | 已实现基础 | builder、fixtures、trajectory evaluator、audit、limits；尚未覆盖所有 Phase B-E |
| Skill/Plugin/MCP | 未使用 | 仓库无 MCP server、Skill registry、插件运行时或 Shell/File Tool |
| Subagent | 受限 | Briefing Agent 是短生命周期独立 `create_agent()`；不是 Time Steward 任意生成子 Agent |

与普通 LLM Chain 的区别在于：这里存在持久 thread、业务 Tool/Service、运行上下文、审批中断、后台执行和可重放事件；但不能因此声称具备 Supervisor、Reflection、MCP 或通用多 Agent。

## 六、Tool Calling 与工具系统

### 6.1 工具分组

`apps/agents/tools/__init__.py` 实际注册 40 个 Time Steward Tool：时间、Event、Task、Reminder、Planning、Decision Profile、Integration status、Insight 和 Briefing handoff 的读写分组。源码约有 45 个 `@tool` 定义，部分细粒度 Event 写入通过 `mutate_events` 组合入口暴露，因此两者不能混称。

项目自研 Tool 通过 LangChain `@tool`/Pydantic schema 暴露；Briefing 使用独立只读 research Tool。没有 MCP Tool、文件 Tool、Shell Tool 或外部 Skill Tool。

### 6.2 一次 Tool 调用的真实链路

```text
Tool Schema / description
  -> Model emits name + structured args
  -> ToolPolicyMiddleware filters read/write set
  -> HumanInTheLoopMiddleware checks risk/conflict
  -> ToolAuditMiddleware begin/idempotency lookup
  -> ToolRuntime context + argument validation
  -> Application Service (ownership/state/version/transaction)
  -> ORM/Provider
  -> ToolMessage (bounded structured result)
  -> next model turn
```

Schema 解决类型和结构，不等于业务合法性；业务参数、权限、资源归属、状态机、时间冲突和幂等由 Service 再校验。`ToolAuditMiddleware` 对同一 `tool_call_id` 已完成调用返回存储结果，正在运行则拒绝重复接管，失败则不盲目重放。

### 6.3 关键 Tool 行为

- `list_events/list_tasks/find_free_slots`：只读，按 actor、时区和时间窗口查询；分页/摘要能力以各 Tool schema 为准，超长结果没有通用外置对象存储机制。
- `mutate_events`：组合 create/update/cancel；相对时间经 Temporal Service 解析；写入前 conflict preview；高风险或用户偏好要求时 interrupt；最终 EventService 事务落库。
- Task/Reminder 写 Tool：调用 TaskService/ReminderService，创建/状态变化受状态机、唯一键和目标归属保护。
- `recommend_task_duration/get_capacity_forecast/record_task_duration_feedback`：读取/写入 Decision Profile Service；推荐是软输入，不直接改日程。
- Planning Tool：创建、比较、验证、锁定/放弃、局部重生成、apply；apply 前复验，涉及高影响变更时 HITL。
- Insight Tool：读取证据并处置；定时 Detector 不由 Agent 触发。
- `transfer_to_briefing`：把规范化请求和消息序列交给父图；不直接完成 Briefing。

Tool timeout 主要来自模型/Worker/Celery 和 Provider 层的有限超时；没有统一每个 Tool 的独立 deadline registry。Retry 只允许 middleware/Provider/Celery 配置次数，写操作依靠 audit/idempotency/version 降低重复副作用。Tool 输出由 schema/Service 返回结构控制，尚未建立通用分页 token 或大结果外置存储，复杂历史查询仍可能增加上下文。

## 七、Context Engineering

### 7.1 进入模型的上下文组成

一次 Time Steward 模型请求由以下部分组成：

1. 基础系统 Prompt：`apps/agents/prompts/time_steward.md`。
2. `runtime_system_prompt` 动态追加：本次 local/UTC anchor、IANA timezone、locale、read/write mode、用户偏好和相对时间规则。
3. Tool descriptions/schema：由当前 Tool Policy 过滤后的工具集合。
4. Checkpoint conversation messages：Human/AI/ToolMessage；当前请求追加 `run_anchor_datetime_utc`。
5. Time Memory 候选：按 intent、衰减、优先级和 800 token 预算注入；不是向量检索。
6. Tool result/Observation：按 Tool 返回结构进入下一轮；审计字段不全部注入模型。

`RuntimeContext` 由服务端构造，包含 actor/user ID、request/agent run/conversation ID、timezone、locale、anchor、trigger、read_only、planning snapshot；用户不能通过 Prompt 覆盖。用户消息、日程标题、天气/news/provider 结果视为不可信数据，不是系统指令。

### 7.2 历史、摘要和超长上下文

`TemporalContextMiddleware` 只在模型请求副本中给历史 Human/AI 内容加旧 anchor 标记并删除历史 `get_current_datetime` 配对消息；checkpoint 中原始对话保留。`SummarizationMiddleware` 默认达到 24 条消息时触发，保留 12 条（配置来源 `agent.yaml`）；摘要是框架能力，项目未自定义事实数据库摘要格式。

存在 Memory 800 token budget 和消息摘要，但没有统一 Agent 总 token budget、结果外置存储、跨子 Agent context compaction 或 prompt cache 开关。模型供应商可能自行缓存，但项目没有配置或指标证明 prompt cache 命中；不能写成“支持 Prompt Cache”。

## 八、Memory

### 8.1 短期与长期

- 短期：Conversation/AgentRun messages + LangGraph PostgreSQL Checkpointer，按 `thread_id` 恢复，隔离用户/会话。
- 长期：从 PostgreSQL 业务事实派生 Time Memory，写 LangGraph Store；保存常用地点、工作节奏、估时/安排习惯等时间决策相关结论，不保存无关对话。

### 8.2 写入、召回和治理

写入链：Event/Task/Execution signal 产生事实 → `transaction.on_commit`/防抖刷新 → `TimeMemoryAnalyzer` 统计 7/30/180 日窗口 → ranking/decay/priority → Store。不是每轮对话直接让 LLM 写 Memory；是否纳入由 Memory Policy、用户开关和数据类型约束决定。

召回链：请求 intent 分类 → 选择 current_load/long_term_habit/location 等候选 → 时间衰减和样本/优先级排序 → 800 token budget 截断 → middleware 注入。用户可关闭生成、关闭注入、reset、删除单项或 exclusion。低样本、过期、schema 不匹配不注入。

Memory 与业务事实用户隔离，Store key 带用户边界；刷新由 Celery/Service 完成，但没有独立的跨实例 Memory CAS/version 协议，依赖任务幂等和可重建设计。潜在污染包括错误执行信号、错误用户输入和历史事实被错误归纳；当前通过 Policy、untrusted 标记和用户纠正缓解。长期个体估时提升、污染率、召回准确率没有真实评测，**需要补测**。

## 九、后端 API 与服务设计

API 是 REST + SSE 混合：资源和动作使用 DRF REST，Agent 增量使用 SSE；没有 WebSocket/RPC。典型边界为 `urls.py -> views.py -> serializer -> service -> ORM/provider`，Agent 是 `views -> AgentRun -> Celery -> execution -> OuterGraph -> Tool -> Service`。

长任务不使用同步 HTTP，因为模型/Tool/Provider 有不确定延迟，且需要审批、取消和断线后继续。创建请求返回 AgentRun/conversation 标识；Celery Worker claim 后执行，客户端用 `/chat/runs/<id>/events/` SSE 读取 `AgentEvent`。断连不取消任务，重连用 cursor；显式 cancel API 才改变运行状态。

内部服务认证使用 actor、Session/Token 和服务端 RuntimeContext；每个查询/写入以当前用户 ownership 过滤。AgentRun 跨 Worker 通过数据库状态 claim；Celery task 使用 `acks_late`、worker lost reject、soft/hard time limit。多个用户可并行，单用户写边界由数据库锁控制。

## 十、异常处理与可靠性

| 故障 | 当前现象/定位 | 当前处理 | 状态与局限 |
|---|---|---|---|
| LLM timeout | Provider/LLM audit error + AgentRun failed | 模型 retry 上限、Celery soft/hard limit | 无统一 circuit breaker；需要补测 |
| LLM 429 | Provider 状态/错误类型 | 有界 model/provider retry；fallback 仅有备用模型配置时启用 | 退避/jitter 依配置和 SDK，未做统一容量实验 |
| LLM 鉴权失败 | Provider error | fail closed，记录 sanitized error | 不自动切换未配置模型；需要补测 |
| Tool timeout | Tool/Worker task 超时 | Tool retry 或 AgentRun fail；写入依赖事务/审计 | 没有所有 Tool 统一独立 timeout |
| Tool 参数错误 | schema/Service ValidationError | ToolErrorMiddleware 转可恢复 ToolMessage/失败审计 | 模型可能继续改参；需要 trajectory 覆盖 |
| Tool 重复执行 | 同 tool_call_id/audit 已完成或 running | 返回已存结果/拒绝重复；Service 幂等键和唯一约束 | 外部未知提交场景仍需 Provider 级验证 |
| Agent 死循环 | recursion/model/tool call limit | limit 异常、安全退出 AgentRun | 无语义 loop detector |
| 数据库失败 | ORM/连接异常、health ready 失败 | transaction rollback，AgentRun failed；容器 health/restart | 自动恢复和连接池上限需补测 |
| 缓存失败 | Redis broker/backend 不可用 | Celery 任务无法执行/ready 失败 | Redis 是否可降级需按路径验证；无业务 Cache fallback |
| 消息队列失败 | Celery publish/worker lost | acks_late/reject_on_worker_lost；任务可重试 | 没有独立 DLQ 设计 |
| 网络断开 | Provider/客户端连接错误 | Provider retry；客户端 SSE 可重连 | 外部副作用未知提交仍需人工处理 |
| SSE 断开 | 前端 cursor 中断 | Agent 继续；按持久 AgentEvent cursor 重放 | 长连接并发/p95 需补测 |
| Worker 重启 | task 被回收或 lost | `reject_on_worker_lost`、stale run recovery、claim | 中断点恢复只对 checkpoint/HITL 有保证 |
| Agent 执行一半崩溃 | AgentRun running/failed，Tool audit 留痕 | 事务回滚；可重试/人工检查 | 非数据库外部写副作用不能自动证明未提交 |
| Checkpoint 读取失败 | LangGraph persistence exception | run failed，记录错误 | 无跨存储 checkpoint fallback |
| 外部副作用未知提交 | timeout 后无法确定 Provider 是否已写入 | fail closed，避免盲目重试；依 provider identity/idempotency | Google 当前只读，外部写回未实现，仍需设计 |

已实现的保护包括 retry 次数、timeout、transaction、optimistic lock、`select_for_update`、idempotency、checkpoint、resume、HITL、graceful task limits。未发现完整 circuit breaker、dead-letter queue、fencing token 或通用 outbox；不能声称已具备。

## 十一、数据库、缓存与消息系统

### 11.1 PostgreSQL

PostgreSQL 是唯一业务事实源。核心表包括 User/Preference、CalendarEvent/EventSeries、Task/TaskExecutionSignal、Reminder、Conversation/AgentRun/AgentEvent/ToolAudit、ActionProposal、SchedulePlan/ChangeBatch/AutomationPolicy、TimeMemory/DecisionFeedback、TemporalInsight、NotificationDelivery、CalendarSyncConnection。关键约束为 user ownership、事件 version、唯一 idempotency/dedup key、外部身份约束和时间查询索引。

写入使用 Application Service 和 `transaction.atomic`；事件更新使用 expected version/乐观锁；同用户日程写操作有事务级串行化边界；审批和撤销使用 `select_for_update`/version。Django 默认数据库隔离级别未在项目中改成 SERIALIZABLE；慢查询、连接池和生产容量**需要补测**。

### 11.2 Redis/Celery

Redis 在 Compose 中作为 Celery broker/result/backend 和运行时协调依赖；当前代码没有证据表明它承担通用业务 Cache、Memory Cache 或可查询 MQ stream。提醒/简报/洞察/Memory/日历 polling 由 Celery task/Beat 调度。Celery 有 ack late、有限重试和 task time limit；没有项目自建 outbox 或 DLQ。任务重复消费靠 Service 幂等，而非队列 exactly-once。

## 十二、并发与一致性

| 场景 | 当前机制 | 边界 |
|---|---|---|
| 两个 Agent 同一 Thread | checkpointer thread + AgentRun claim/context 校验 | 同 thread 并发模型效果需压测 |
| 两个 Worker 同一任务 | `claim_for_execution/resume` + 状态条件 | claim 失败返回现状 |
| 重复提交 | AgentRun operation/request、Service 幂等 | 所有 API 的统一幂等覆盖需补测 |
| Tool retry 重复写 | ToolAudit tool_call_id、unique keys、transaction | 外部副作用未知提交仍不自动解决 |
| 多 Agent 修改资源 | Event version、用户 schedule write lock、冲突复验 | 外部写回未实现 |
| 多实例更新 Memory | on-commit、防抖、可重建 Store | 没有通用 fencing/CAS，需补测 |
| SSE 重连 | PostgreSQL AgentEvent cursor/replay | 事件保留和高并发需补测 |
| Worker 崩溃 | ack late/reject lost/stale recovery/checkpoint | 非 checkpoint Tool 的中间状态要人工判定 |

已实际使用 transaction、unique constraint、optimistic lock、row lock、idempotency key、Celery queue；没有证据表明使用 distributed lock lease、fencing token、通用 outbox、MQ exactly-once。

## 十三、模型调用与成本

模型配置在 `backend/config/agent.yaml`/example 和 `apps/agents/configuration.py`，支持 `openai_compatible`、Anthropic provider 和 alias；默认模型、备用模型、briefing model 可配置。Time Steward 由 `create_agent()` 绑定 Tool calling；Briefing 也是 `create_agent(response_format=...)`。项目没有 Vision Tool、租户级模型选择或按用户动态模型策略。

模型调用由 `LLMUsageMiddleware` 写 `LLMCallAudit`：input/output/total tokens、memory prompt tokens/ratio、model、component、duration、status、request ID。Model/Tool retry 默认 2；Agent limits 为 model 8/tool 16/graph recursion 50。具体 temperature/max_tokens/streaming 由 provider/model config 决定，不能从框架存在推断所有模型都支持。

评测中的 Token/Task 是按 request ID 聚合的 LLM audit total tokens，包含每轮输入/输出；不是上下文窗口大小，也不是单个 Tool result token。子 Agent Briefing 有独立 component/run，但没有统一跨 Agent 成本归集报表。当前无模型单价配置、真实账单或成本/Task，成本分析**需要补测**。

## 十四、性能与资源

已知仅有一次真实离线 Agent 评测：主集 p50 `2.89s`、p95 `8.02s`、Token/Task `18,367.31`；这是 13 例小样本，不代表 API/SSE/Tool/生产 p95。项目没有 TTFT、p99、QPS、并发用户、数据库耗时、Redis lag、CPU/内存/GPU 或成本数据，均为**需要补测**。

性能瓶颈的代码层推断：模型多轮和大 Tool schema/历史是 Agent 主要成本；外部 Provider、数据库查询和 SSE 长连接是后台/接口成本。可优化方向是 deterministic pre-routing、并行只读 research sections、结果摘要/分页、减少重复 Tool call、按任务路由模型、异步化非交互工作；这些是方案，不是已测收益。提醒、洞察、简报已异步化；Time Steward 仍是多轮模型执行。没有 prompt cache 命中证据。

## 十五、评测体系

### 15.1 测试层次

- 后端 pytest-django：模型、Service、API、Agent middleware/trajectory、Planner/Memory/Insight/Provider；最近文档记录 SQLite 和一次性 PostgreSQL 17 各 `474 passed, 3 skipped`，当前工作区新增测试需重新跑全量。
- 前端 Vitest/RTL：页面、hooks、navigation、API 交互；Playwright fixture E2E 验证桌面/移动关键流程。
- 契约：DRF schema → `backend/openapi.json` → `frontend/src/api/generated/schema.d.ts`。
- Agent trajectory：`evaluate_time_steward` 真实模型执行固定 fixture，校验 required/allowed/forbidden Tool、响应泄漏模式、相对时间参数和 Token/Latency。

### 15.2 Benchmark 和真实结果

| Benchmark | Baseline/实验组 | Metric | 当前结果与可信度 |
|---|---|---|---|
| Agent trajectory | 固定 Prompt/Tool/模型，主集 | Task Success、Tool recall/precision、constraint、Token、p95 | `12/13`、`95.83%`、`100%`、`100%`、`18,367`、`8.02s`；单次小样本 |
| Temporal ablation | 完整 vs 移除 TemporalContextMiddleware | 同上 | 6/6 两组均 100%；无质量增益结论 |
| Planning | first-fit vs longest-first-best-fit | placement/tasks/minutes/overlap | 7→8 tasks、390→480m、0 overlap；合成边界集 |
| Adaptive planning | full compaction vs bounded local repair | moved/total movement/deadline/overlap | 1→3 items、60→480m、0 violations；只证明固定案例可运行 |
| Memory | fixed30/user/global/stratified | 时序留出 MAE/calibration/fallback | 命令和测试存在；真实样本不足，需补测 |
| Insight/Attention | detector + policy | precision/recall/action/dismiss/false positive | 计算链存在；无真实观察窗口，需补测 |

当前没有 LLM-as-judge、统计显著性、置信区间、线上 A/B 或用户完成率实验。`today-schedule` 主集唯一失败为漏调用 `list_tasks`，应作为回归 case，不能把 `92.31%` 写成产品成功率。

### 15.3 推荐补测

扩展 Phase B-E golden set；同一模型重复多次，报告均值/方差；分别消融 anchor、历史标注、relative Tool schema；加入跨午夜/DST/时区/旧指代、Memory 冲突、Plan 失效、HITL 恢复、Provider stale 和 prompt injection。规划使用脱敏真实周计划，比较 first-fit/EDF/priority/CP-SAT；Memory 使用严格时间切分；主动能力用人工标注和通知行动/关闭窗口；API/SSE/Celery/Agent 分开负载测试。

## 十六、可观测性

一次请求通过 `X-Request-ID` 关联浏览器、Nginx、Django 和 LLM audit；AgentRun/AgentEvent/ToolCallAudit/ActionProposal/BriefingRun/NotificationDelivery 形成业务 trace-like 轨迹。`LLMCallAudit` 记录 sanitized usage/status/duration，不保存完整 Prompt、回答、Token、Cookie 或私有推理。

Prometheus 是低基数业务 SLI：Agent/Tool/Briefing/Notification 24h 结果、Agent p50/p95、stale runs、Proposal、逆地理编码、LLM 调用和 Token。Grafana/Loki/Alloy/Alertmanager 是可选 Compose overlay；label 不应放 user ID/request ID。LangSmith/Langfuse/OpenTelemetry 没有接入证据。当前支持 bad case 按 request ID 回查，但没有自动把线上失败回流 golden set；告警送达与长期数据保留需补测。

## 十七、Docker 与部署工程

生产链路：

```text
Docker image start
  -> Django settings.production / env validation
  -> PostgreSQL + Redis health
  -> Uvicorn ASGI on internal 8000
  -> Celery worker/beat start
  -> frontend Nginx static files
  -> entry Nginx proxy + Cloudflare Tunnel
  -> API/Agent request -> SSE/HTTP response
```

Compose 服务包含 PostgreSQL 17、Redis 7、Django/Uvicorn、Celery worker/beat、frontend Nginx、入口 Nginx 和可选 Prometheus/Grafana/Loki/Alertmanager/exporter。Nginx 对 SSE 关闭 buffering/cache 并保留长 timeout；APK 静态文件严格路径、HTTPS 元数据和 hash/signature 校验。数据 volume、healthcheck、restart policy、内外端口、生产 overlay 和备份恢复脚本均存在。

当前没有 Gunicorn/WSGI；ASGI 使用 Uvicorn。Secret 通过环境变量/服务端配置，不进 `VITE_*`。迁移需先 check/makemigrations；PostgreSQL custom-format backup/restore 有脚本，但隔离恢复演练、完整 graceful shutdown、横向 worker 和回滚时间**需要补测**。

## 十八、真实技术难点复盘

### 难点 1：异步多轮 Agent 的相对时间漂移

- **现象**：同一“明天/两天后”请求在排队或重试后可能落到不同日期。
- **定位**：检查 `RuntimeContext`、`state_from_trigger`、时间 Tool 和 `779435d`/时间回归测试。
- **根因**：把机器隐式 now 当成业务时间；历史 AI 的 clock Observation 会污染当前上下文。
- **方案**：run anchor + UTC/IANA；历史消息加旧 anchor 标签、删除旧 clock 配对；相对写入使用 relative schema。
- **结果/证明**：固定 Agent Eval 和 6-case 消融通过；消融未显示独立质量增益。
- **局限**：更复杂 DST/跨时区/歧义数据和重复运行仍需补测。

### 难点 2：HITL 审批恢复与竞态

- **现象**：重复 approve、Worker 抢占、proposal 过期可能导致重复写入或状态不一致。
- **根因**：审批决定、业务写入和 Agent resume 是跨阶段操作。
- **方案**：`ActionProposal` 持久事实、TTL/version、`select_for_update`、幂等决定、interrupt/resume、Service 二次校验。
- **结果/证明**：approve/edit/reject/expire/failed 测试覆盖；真实并发压测需要补测。
- **为什么不用前端确认**：前端状态可被重复请求绕过，不能保护数据库和 Worker。

### 难点 3：PostgreSQL SSE 连接污染

- **现象**：SQLite 通过而 PostgreSQL 17 SSE 轮询出现 psycopg `BAD` connection。
- **根因**：事务内无条件清理数据库连接，破坏当前事务连接状态。
- **方案**：只清理非事务连接，增加一次性 PostgreSQL 全量回归。
- **结果**：历史记录为 SQLite/PostgreSQL 各 `474 passed, 3 skipped`；连接长期稳定性仍需补测。

### 难点 4：洞察通知幂等键与不可变投递

- **现象**：升级扫描因 payload、剩余小时和 decision time 变化而复用旧 key，被 Notification Service 拒绝。
- **根因**：同一 key 同时表示“同一次投递”和“随时间变化的内容”。
- **方案**：保留首次 decision anchor、版本化 key、已物化 Delivery 按 source/channel 视为不可变事实。
- **结果**：升级兼容/重复扫描回归已覆盖；真实通知窗口需补测。

### 难点 5：Planner 的可行性与稳定性

- **现象**：first-fit 顺序贪心让长任务被短任务占用的槽位挤出，失败原因不透明。
- **方案**：确定性排序/ best-fit、hard gate、unplaced reason、草案 TTL/version、apply 前重验；局部重排加 allowlist/move cap/撤销。
- **结果**：固定合成案例安排 7→8、390→480 分钟、零重叠；不能外推真实收益。

### 难点 6：Android 安装器旧元数据

- **现象**：应用显示可下载新版本，但系统安装器显示旧版本。
- **定位/根因**：APK manifest/hash/signer 正确，最符合证据的是固定 FileProvider URI 被 OEM 安装器缓存；无设备日志，根因仍是推断。
- **方案/结果**：版本号+hash 文件名、清理旧包、禁用 HTTP cache、安装前版本校验；1.1.7 公网回下载通过，真机矩阵未验证。

## 十九、技术选型与 Trade-off

| 当前方案 | 替代方案 | 解决的问题 | 代价/边界 |
|---|---|---|---|
| Django 模块化单体 | FastAPI 微服务 | 统一 ORM/事务/Admin/契约 | 单体发布，后台需队列隔离 |
| `create_agent()` + Outer Graph | 手写 ReAct/全 Graph 节点化 | 复用官方循环、HITL、middleware；Graph 只做业务路由 | 框架消息协议和升级测试成本 |
| PostgreSQL 事实 + Store 派生 Memory | 只用聊天/向量库 | 一致性、删除、重算、审计 | 需维护事实→画像 pipeline；没有通用 RAG |
| 确定性 Planner | LLM 直排/CP-SAT | 可解释、可复现、快 | heuristic 不保证全局最优；CP-SAT 后续按真实问题引入 |
| Celery Beat/Worker | APScheduler/云任务 | 到期、重试、后台解耦 | Redis/Celery 运维和重复消费设计 |
| SSE | WebSocket/轮询 | 单向增量、HTTP 简单、cursor 恢复 | 代理 timeout、连接和重放需治理 |
| Provider Protocol | 业务直接依赖 SDK | 替换、mock、降级、能力声明 | DTO/错误语义维护成本；部分 Provider 未验收 |
| Session + Native Token | 全 JWT/OAuth | Web 同源和 Capacitor 跨源各用合适认证 | 双路径测试和安全边界 |
| Capacitor 复用 React | 原生 Android/Flutter | 低重复、快速复用业务页面 | 原生通知、后台和安装兼容复杂 |
| 自托管 APK | Google Play In-App Update | 当前无商店链路仍可发布 | 签名保管、未知来源、OEM 兼容责任 |

## 二十、项目不足与后续优化

1. **真实价值未证明**：当前有工程闭环但没有 DAU、留存、完成率、MAE 改善和通知行动率；先做脱敏行为/反馈采集和时间切分评测。
2. **Agent 固定集覆盖不足**：主集唯一失败为聚合查询漏 `list_tasks`；扩充 Phase B-E trajectory，重复运行并设置发布门禁。
3. **Planner 非全局最优**：真实计划数据到位后比较 EDF/CP-SAT/局部搜索，硬约束先 gate，再看按期率/碎片/移动距离。
4. **Memory 无跨实例 CAS**：当前靠可重建和任务幂等；若实测刷新冲突，再引入版本/lease，而不是提前创建空抽象。
5. **缺通用熔断/DLQ/outbox**：当前路径依靠有限 retry、fail closed 和幂等；在 Provider/队列故障压测后决定是否需要这些组件。
6. **外部日历和通知未真实验收**：Google 沙箱 OAuth/410/429/撤权、通知送达窗口、Android 设备矩阵均需补测。
7. **上下文成本未优化**：Memory 消融未证明收益，Tool schema/历史可能导致 token 增长；拆分变量并报告重复实验后再删减。
8. **工作区提交边界混杂**：Phase A-E 和 Android/前端修改横跨大量文件；应按领域拆提交，保留 ADR 和可回滚发布单元。

## 二十一、面试深挖问题（30 题）

1. 为什么 Time Steward 用 `create_agent()`，Outer LangGraph 仍然需要？
2. 为什么不把每次模型/Tool 调用都手写成 Graph node？
3. `AppState`、`TimeStewardState`、`RuntimeContext`、checkpointer、Store 分别保存什么？
4. 为什么 `user_id/thread_id` 不在 Agent State 字段里？
5. “明天”在排队、重试和多轮中如何保持一致？
6. DST 不存在/歧义时间如何处理？只存 UTC 为什么不够？
7. 历史 `get_current_datetime` 为什么要从模型副本中删除？
8. 40 个注册 Tool 会不会影响选择？为什么用 `mutate_events` 收敛写入口？
9. Tool schema 校验和 Service 业务校验分别解决什么问题？
10. Tool 为什么不能直接访问 Django ORM？
11. 哪些写操作需要 HITL？冲突创建为何有条件地自动通过？
12. approve 重复提交、proposal 过期和 Worker 重复接管如何处理？
13. 为什么必须恢复同一个 LangGraph thread？
14. Reminder 为什么不能经过 LLM？Beat 重启如何避免重复通知？
15. Agent recursion limit、model/tool call limit 和 Celery time limit 是什么关系？
16. 当前是否有 loop detector、circuit breaker、DLQ？没有会有什么风险？
17. SSE 为什么不用 WebSocket？断线、代理缓存和 cursor 如何处理？
18. PostgreSQL SSE `BAD connection` 如何定位和修复？SQLite 为什么没发现？
19. Memory 为什么不是 RAG？它的写入、召回、删除和用户隔离如何保证？
20. 为什么 Briefing 不消费 Time Steward Memory？
21. 实际工时为什么不能用完成时间减开始时间？
22. 个体估时为什么必须时间切分，不能随机切分？
23. Planner 为什么不用 CP-SAT？heuristic 的失败模式是什么？
24. `SchedulePlan` 为什么保存 snapshot、TTL、version？Apply 前为什么重验？
25. TemporalInsight、AttentionPolicy、NotificationDelivery 为什么分三层？
26. 统一幂等键为什么会导致洞察通知升级失败？
27. Redis 在本项目中到底承担 Cache、Queue、Lock 还是 Result Backend？
28. Tool retry 遇到外部“未知提交”为什么不能保证 exactly-once？
29. 当前 Token/Task、p95 和 92.31% 评测结果的统计边界是什么？
30. 哪些代码是上游框架能力，哪些是你真正设计/修改的？如何用提交、测试和故障记录证明？

回答每题时都应先给当前代码事实，再给设计理由和替代方案，最后主动说出未验证边界；不要把“理论上可扩展”说成已实现。

## 二十二、最终输出总结

### 22.1 最有竞争力的技术亮点

1. 将受控 Agent 接入真实时间事务：`RuntimeContext + Tool Policy + Service + HITL + Audit`。
2. 解决异步、多轮 Agent 的时间确定性：run anchor、UTC/IANA/DST 和历史上下文清洗。
3. 从执行信号到个体估时、容量和 Planner 的可审计闭环。
4. 可解释、可复验、可撤销的 Planner/局部重排，而非模型直接改日历。
5. Agent 与 Celery/通知/Provider/Android 工程链路解耦，支持生产排障和跨端触达。

### 22.2 最值得写进简历的成果

- 设计并落地 Time Steward Agent 业务边界，注册 40 个 Tool，接入日程/任务/提醒/规划真实服务。
- 建立 ActionProposal/HITL、版本保护、幂等审计和 checkpoint resume 的高风险写入闭环。
- 实现确定性 Planner v2 和受控局部重排；固定合成集安排任务 7→8、有效安排时长 390→480 分钟、零时间重叠（仅合成证据）。
- 建立 13 场景/14 轮真实模型 trajectory 评测，报告 Task Success `92.31%`、Tool Recall `95.83%`、p95 `8.02s`，并保留失败案例。
- 完成 Web/Android/Compose/Nginx/Celery/Prometheus 等跨端和生产链路；真实用户收益与设备矩阵仍需补测。

### 22.3 最值得重点讲的技术难点

1. 相对时间在异步多轮运行中的漂移与历史污染。
2. HITL 审批、Worker 竞态和 exactly-once-like 业务语义。
3. 确定性排程与局部重排如何在可行性、稳定性和用户控制之间取舍。

### 22.4 缺失实验与 Benchmark

真实用户规模/留存/完成率、个体估时 MAE、规划真实可行性、主动通知 precision/recall/action rate、Agent 重复运行稳定性、Tool argument accuracy、TTFT/p99/QPS、Token 成本、Provider 和 Android 真机矩阵均需补测。优先级是：Agent B-E golden set → 时间消融重复实验 → 脱敏真实计划/执行数据 → API/SSE/Worker/Agent 分层压测 → Provider/设备验收。

### 22.5 不能写进简历的表述

- “完整多 Agent Supervisor/Reflection/MCP/RAG 系统”：当前没有。
- “92.31% 用户任务成功率”或“提升用户效率”：当前只是小规模离线模型 Eval。
- “规划算法全局最优”“个体估时显著提升”：当前只有合成 benchmark，真实数据不足。
- “所有机型均保证后台通知/自更新”：Android 真机矩阵未完成。
- “Redis 提供业务缓存/MQ exactly-once”“Agent 自动执行所有主动任务”：代码证据不足或与确定性 Celery/HITL 边界冲突。

### 22.6 30 秒介绍

> Time Agent 是我主导的个人时间管理 Agent，面向需要同时管理日程、任务和截止时间的知识工作者。它把自然语言理解交给受控 Agent，把时间计算、冲突、权限、审批和通知交给确定性后端，从而支持规划、执行、长期个性化和主动提醒。我重点完成了 Agent 与事务系统边界、可恢复 HITL、时间锚点、Planner/Memory 和评测链路。目前 Web 和 Android 已部署，固定模型集 13 个场景通过 12 个；真实用户价值仍在验证。

### 22.7 2 分钟介绍

> 项目要解决的是日历、待办和提醒互相割裂，用户无法判断任务是否真的能在截止前完成。我的设计不是让 LLM 直接改数据库，而是让 PostgreSQL 成为唯一事实源：Time Steward 用 `create_agent()` 理解请求并选择 Tool，Tool 只能通过 Application Service 访问业务数据，Outer LangGraph 负责 trigger 路由、Briefing handoff 和 interrupt/resume。所有相对时间使用显式 run anchor，所有写操作经过权限、冲突、版本和幂等校验，高风险操作落成 ActionProposal，审批后恢复同一 thread。长期能力从执行信号派生估时和容量画像，Planner 生成可解释草案，主动洞察和提醒则由 Celery/Notification 状态机确定性执行。真正难点是异步时间语义、审批竞态和计划重排的稳定性。当前已经有 Web/Android/生产部署和 13 场景真实模型评测，但评测样本小，个体化收益、并发和长期用户数据还不能夸大。

### 22.8 一次完整 Agent 请求的口述版

> 用户请求先经过 Session 或 Android Token 认证，后端创建带 conversation、run anchor 和 request ID 的 AgentRun，交给 Celery。Worker 构建 RuntimeContext 和 TriggerEnvelope，Outer Graph 路由到 Time Steward。`create_agent()` 将系统规则、当前时间、用户偏好、允许的 Tool 和 checkpoint history 交给模型。模型产生结构化 Tool call 后，middleware 先检查 read/write policy、HITL 和审计，再由 Tool 调 Application Service；Service 在事务中做用户隔离、参数、版本、冲突和幂等校验，最后写 PostgreSQL 并返回 ToolMessage。模型根据 Observation 决定继续查询、澄清或输出答案，AgentEvent 持久化后由 SSE 按 cursor 推送。若是高风险写入，流程在 interrupt 处停住，用户审批后用同一 thread resume；若是提醒或定时简报，则直接走 Celery/Briefing Workflow，不调用 Time Steward。

### 22.9 “这是我真正做的吗？”证据清单

- **代码**：`apps/agents/agents/time_steward.py`、`middleware.py`、`outer_graph.py`、`state.py`、`context.py`、`tools/`、`conversations/execution.py`。
- **业务闭环**：`action_proposals/services.py`、`events/services.py`、`planning/`、`time_memory/`、`briefings/`、`notifications/`、`reminders/dispatcher.py`。
- **测试**：`backend/tests/test_time_steward_agent.py`、`test_graph_execution.py`、`test_action_proposals.py`、Planner/Memory/Insight/Provider 测试、前端 RTL/Playwright。
- **评测**：`backend/apps/agents/management/commands/evaluate_time_steward.py`、两个 fixture、`docs/operations/evaluation-results-2026-08-25.md`。
- **工程**：Docker Compose、Nginx、Celery、备份脚本、Prometheus/Grafana/Loki 配置、Android build/release 文档。
- **提交**：`dd0bd49`（Time Steward）、`7e1f7db`（HITL）、`f3b2b8b`/`d8faf55`（Briefing）、`04dfd50`（Notification）、`779435d`（相对时间）。
- **边界**：未提交工作区不能单独证明个人归属；真实用户、Provider、设备、并发和长期收益没有证据时，统一说“需要补测”。
