# Time Agent：AI 原生产品战略与未来演进路线

> 状态：产品与技术方向底稿，尚未代表已实现能力
>
> 更新日期：2026-08-23
>
> 适用范围：产品定位、智能能力边界、未来架构和分阶段实施优先级

## 1. 文档定位

本文是在完整复核当前代码、配置、测试、架构文档和既有路线图后，对 Time Agent
未来方向形成的上位理解。它回答的是“这个产品下一步应该成为什么”，不是“当前代码已经支持什么”。

文档关系如下：

- 当前已交付 Phase 0 至 Phase 10 的范围和状态，仍以根目录 [ROADMAP.md](../../ROADMAP.md)
  为准；本文不重写历史交付记录。
- 当前系统行为以 [PROJECT_SPEC.md](../../PROJECT_SPEC.md)、`docs/architecture/` 和
  `docs/decisions/` 为准；本文中的目标架构不能覆盖已采纳 ADR。
- 每日收尾、主动洞察、规划智能和自适应重排均直接以本文的阶段路线和边界为准；不再维护单独的
  每日收尾下位路线图。
- 任何新增 Agent、持久化边界或部署拓扑，开始编码前仍须编写 ADR；本文本身不是 ADR。

本文暂时放开既有功能路线的限制，但不放开工程纪律。PostgreSQL 业务事实权威、
Tool 到 Application Service 的调用边界、确定性提醒、HITL、UTC/IANA 时区、有限调用和
Provider 可替换等规则继续成立。

## 2. 最终结论

### 2.1 一句话定位

**Time Agent 应成为一个个人时间操作 Agent：持续把目标、承诺、行为证据和变化中的上下文，
转化为现实、可解释且由用户控制的时间分配，并根据执行结果学习和调整。**

### 2.2 它不只是 Calendar + Chatbot

Calendar + Chatbot 主要缩短“表达意图到 CRUD”的路径，例如用自然语言创建事件、查找空闲时间。
Time Agent 真正值得形成差异的地方，是闭合下面的循环：

```text
目标与承诺
  -> 约束和偏好
  -> 可执行计划
  -> 日历中的时间承诺
  -> 完成、延期、跳过和打断等执行证据
  -> 个体规律与风险判断
  -> 建议、确认或有限自动执行
  -> 新的计划与反馈
```

当前项目已经把“事实、受控操作和交付”做得较扎实，但闭环主要停在“查询/创建/简报”；
未来竞争力应来自个人化决策质量、对变化的适应能力和克制的主动性，而不是继续增加聊天命令或新闻源。

### 2.3 目标用户与核心场景

第一目标用户不是需要企业排班、团队资源管理或复杂审批流的组织，而是同时面对任务、日历和临时变化，
已经感到“维护计划本身很累”的个人知识工作者、学生和自由职业者。他们通常有以下共同问题：

- 任务散落在清单里，却没有被转换成现实可用的时间；
- 知道优先级和截止时间，仍持续低估耗时或高估当天容量；
- 计划一旦被打断，就需要重新手工拼日历；
- 提醒很多，但真正有决策价值的提示很少；
- 通用 AI 能理解一句命令，却不了解这个人的长期时间规律和已做过的取舍。

核心价值主张是：**少花时间维护计划，更早看见不可行，在变化后更快恢复可执行状态，并始终保有最终决定权。**
团队协作、多人会议优化和组织级绩效不是近期主战场；外部日历首先用于补全个人承诺事实。

## 3. 当前系统事实

### 3.1 产品与终端

Time Agent 当前是一个时间中心的个人事务管理系统：

- Web/PWA 与 Capacitor Android 共用 React 前端；Android 额外提供安全 Token、原生通知、
  Deep Link 和应用内更新能力。
- 用户可直接管理事件、任务、提醒、今日视图、简报、审批和时间偏好，也可通过聊天让
  Time Steward 调用同一组业务能力。
- Django 单体后端承载业务事实、API、Agent 运行、审批和调度；PostgreSQL 是唯一业务事实来源，
  Redis/Celery 负责异步与定时工作。

证据入口：`README.md`、`CLAUDE.md`、`frontend/src/app/router.tsx`、
`frontend/src/bootstrap.ts`、`backend/config/urls.py`、`docker-compose.yml`。

### 3.2 当前核心数据

当前真正存在的时间事实主要包括：

- `CalendarEvent`：带时区、状态、版本和冲突规则的确定时间占用；
- `Task`：包含项目字符串、父任务、优先级、截止时间、预计分钟数、计划起止、实际开始和
  完成时间，但没有暂停/恢复轨迹和可靠的实际专注时长；
- `Reminder` 与 `NotificationDelivery`：确定性调度和分渠道投递状态；
- `SchedulePlan`：可审阅的计划草案，不是日历事实；
- `AgentRun`、对话和 `ActionProposal`：运行、流式事件、暂停恢复和高风险审批；
- `BriefingDefinition/Run`：简报定义、运行结果和来源；
- `TimeMemoryRefreshState/Exclusion/Audit`：派生 Memory 的刷新、排除和审计状态。

证据：`backend/apps/events/models.py`、`backend/apps/tasks/models.py`、
`backend/apps/reminders/models.py`、`backend/apps/notifications/models.py`、
`backend/apps/planning/models.py`、`backend/apps/conversations/models.py`、
`backend/apps/action_proposals/models.py`、`backend/apps/briefings/models.py`、
`backend/apps/time_memory/models.py`。

当前没有一等公民的 `Goal`、结构化 Project、洞察收件箱或注意力预算。外部日历已经有
`CalendarSyncConnection`、ICS 与 Google 只读 Provider、加密 OAuth 凭据和 Provider 驱动同步；Google 沙箱尚未验收，
Microsoft、Webhook 与外部写回未实现。

### 3.3 一次聊天请求的真实调用链

```text
React Chat Page
  -> feature API -> frontend/src/api/client.ts
  -> Django chat API / Application Service
  -> 创建 Conversation / AgentRun
  -> TriggerEnvelope(user_message) + RuntimeContext(用户、时区、显式当前时间、限额)
  -> LangGraph Outer Graph 确定性路由
  -> Time Steward: LangChain create_agent()
  -> Middleware: 上下文、Memory、Tool Policy、HITL、重试/回退、限额、摘要、审计
  -> Tool
  -> Application Service
  -> Domain/Repository
  -> Django ORM -> PostgreSQL
  -> AgentRunEvent / SSE -> 前端
```

高风险写操作不会由模型直接完成：Tool 创建 `ActionProposal` 后触发 LangGraph interrupt，用户
批准、编辑后批准或拒绝，随后使用同一 thread 恢复。证据：
`backend/apps/agents/agents/time_steward.py::build_time_steward_agent()`、
`backend/apps/agents/outer_graph.py::build_outer_graph()`、
`backend/apps/agents/middleware.py::build_time_steward_middleware()`、
`backend/apps/action_proposals/services.py`。

### 3.4 非聊天触发链

- `scheduled_briefing` 直接路由到 Briefing Workflow，不先经过 Time Steward；Briefing 使用一个
  短生命周期、只读、结构化输出的 Agent，按 section 调研并保留来源。
- `reminder_due` 进入无状态 `reminder_dispatcher`，由 Celery 确定性执行，不调用 LLM。
- `calendar_webhook` 仍只有外层路由占位；用户触发的 ICS/Google 真实只读同步和有界 Celery 轮询已实现，Webhook 尚未实现。
- Time Memory 由 Celery 按 PostgreSQL 变化确定性重建，再通过 middleware 以有限 Token 注入
  Time Steward；Briefing 不读取 Memory。

证据：`backend/apps/agents/routing.py::TRIGGER_ROUTES`、
`backend/apps/agents/outer_graph.py::reminder_dispatcher_node()`、
`backend/apps/briefings/workflow.py`、`backend/apps/time_memory/tasks.py`、ADR 0015。

### 3.5 当前 AI 能力深度判断

当前 AI 的主要角色是：

1. 理解自然语言并选择受控 Tool；
2. 在真实业务上下文中完成多步查询或操作；
3. 对天气、新闻、日程和任务做简报式综合；
4. 对高风险写入给出可审阅提案；
5. 读取派生的长期行为摘要，改善对话上下文。

它目前还不是持续运行的个人时间决策系统：

- 没有目标到时间分配的模型；
- 没有可靠的计划与实际执行差异数据；
- Memory 主要进入 Prompt，没有作为类型化特征参与排程、提醒或重排决策；
- `PlanningService.propose_schedule_plan()` 按任务 ID 顺序做简单贪心分配，不使用优先级、截止时间、
  精力、个体估时误差或计划稳定性评分；
- 没有常驻的风险检测、介入候选、注意力策略和反馈学习；
- 主动能力主要是固定时间简报和提醒，而不是“发现值得打扰的变化”。

因此，当前系统更准确的定义是：**具备可靠业务边界的时间管理 Agent 基础设施与对话式操作层**。
下一阶段要建设的是决策层和学习闭环，而不是把 LLM 放进更多链路。

### 3.6 当前智能能力矩阵

| 能力 | 当前实现事实 | 判断 |
| --- | --- | --- |
| Context Engineering | `RuntimeContext` 注入用户、时区、locale、显式当前时间、触发类型、只读模式和规划偏好；Tool 输出视为不可信数据 | 较强基础 |
| Tool Use | Time Steward 当前注册 25 个时间、事件、任务、提醒、规划和 Handoff Tool，统一经过 Service 与 Policy | 较强基础 |
| Reasoning | `create_agent()` 在有限轮次内做自然语言理解和多步 Tool Calling，支持模型 fallback | 已有，但主要是请求内推理 |
| Planning | 有空闲时间搜索、`SchedulePlan` 草案与事务应用，但 proposal 只是顺序贪心 | 基础可用，决策质量弱 |
| Memory | 7/30/180 天确定性行为窗口、稳定模式、衰减、排除和 Token 预算注入 | 描述性较强，决策连接弱 |
| Routing/Workflow | 外层 LangGraph 对五类 trigger 确定性路由，支持 Briefing Handoff、interrupt/resume | 边界清楚 |
| Retry/Fallback | 模型、Tool、Briefing repair、Provider 和通知各有有界失败处理 | 已有工程基础 |
| Reflection | 没有独立 Reflection Agent，也没有基于结果的自动自我修正循环 | 尚不存在，且不应先造 Agent |
| Proactivity | 固定提醒、定时 Briefing 和 Memory 重建；没有风险检测与注意力决策 | 调度主动，决策不主动 |
| Evaluation | 单元/集成/E2E、真实模型 trajectory eval、指标和审计 | 工程评测已有，产品效果评测缺失 |

Tool 数量证据来自 `backend/apps/agents/tools/__init__.py` 及各 Tool 模块末尾的注册清单；触发类型来自
`backend/apps/agents/triggers.py::TriggerType`。数量只是当前契约事实，不代表智能水平。

## 4. 竞品中的 AI 到底做了什么

以下只分析公开产品资料可确认的 AI 参与方式，不推测其内部算法。

| 产品类型 | AI/自动化参与点 | 自治与控制方式 | 对 Time Agent 的启发 |
| --- | --- | --- | --- |
| Sunsama | Daily Planning/Shutdown 把回顾、未完成事项处理和明日负载确认串成短仪式 | 用户逐步确认，AI 不是核心卖点 | 晚报应是决策入口，不能只生成一段总结 |
| Motion | 使用可用时间、时长、截止时间、优先级、工作时间和拆分规则自动排程，变化后动态重排 | 明确展示无法安排和过期事项，计划受结构化约束 | 排程价值来自可行性与持续维护，LLM 不应负责时间数学 |
| Reclaim 2.0 | Assistant 发现冲突、过载和缺少专注时间；后台 Agent 优化 focus/habit/buffer；GTD 按上下文推荐工作 | Preview Mode 先集中展示变更，再应用；通过策略和偏好约束 Agent | 主动检测、变更收件箱、预览沙箱比“更主动的聊天”更重要 |
| Clockwise | 根据 Focus Time 目标和会议代价给出多步移动建议，也支持周期性自动优化 | 可按会议授权灵活移动，展示建议原因和取舍 | 自治应绑定对象级授权、可逆范围和优化目标 |
| Akiflow | Daily Ritual、Dashboard 和 briefs 汇总日历、计划任务、时间块与集成信息 | 以用户主导的 time blocking 和锁定为主 | 好的体验可以先有确定性流程，再逐步注入个体智能 |
| Trevor AI | 预测任务时长、推荐排程、Plan My Day 和对话助手 | 用户选择建议并放入日历 | 估时是个人规划模型最早可量化的切入点 |
| Gemini + Calendar | 从对话上下文创建、查询、编辑或取消日历事项 | 对能力范围和不可执行字段有明确限制，并提供撤销/回看 | “会调用日历”已经趋于基础能力，不足以形成壁垒 |
| Microsoft Copilot + Outlook | 对话找共同时间、会议准备；可对用户显式授权的个人/1:1 事件做冲突后自动重排 | 用户指定可接受时间，限制会议类型和自动重排次数，并在通知面板留痕 | 对象级 opt-in、次数上限、失败退出和变更日志是高自治的必要条件 |

公开参考：

- [Sunsama Daily Planning](https://help.sunsama.com/docs/usage-guides/daily-planning/)
  与 [Daily Shutdown](https://roadmap.sunsama.com/changelog/daily-shutdown)
- [Motion Auto-scheduling](https://www.usemotion.com/help/time-management/auto-scheduling)
  与 [How auto-scheduling works](https://www.usemotion.com/help/time-management/auto-scheduling/reference-auto-scheduling/how-auto-scheduling-works-behind-the-scenes)
- [Reclaim 2.0 Overview](https://help.reclaim.ai/en/articles/14846468-reclaim-ai-2-0-overview)
  与 [Reclaim 2.0 FAQ](https://help.reclaim.ai/en/articles/15280604-reclaim-2-0-faq)
- [Clockwise Release Notes](https://support.getclockwise.com/article/84-clockwise-release-notes)
  与 [Flexible Meetings](https://support.getclockwise.com/article/80-accessing-clockwise)
- [Akiflow Time Blocking](https://product.akiflow.com/help/articles/3677363-time-blocking-101)
  与 [Daily Dashboard](https://product.akiflow.com/en/help/articles/7855441-daily-dashboard)
- [Trevor AI Documentation](https://www.trevorai.com/docs)
- [Gemini Calendar Help](https://support.google.com/gemini/answer/15305236?hl=en)
- [Copilot Chat Assisted Scheduling](https://support.microsoft.com/en-us/outlook/schedule-a-meeting-using-copilot)
  与 [Automatic Rescheduling](https://support.microsoft.com/en-us/office/automatically-reschedule-events-with-copilot-in-microsoft-outlook-and-microsoft-teams)

由此得到的产品判断是：行业正在从“自然语言 CRUD”走向“受约束的持续优化”。Time Agent 不应在
日历入口、新闻摘要或聊天 UI 上与平台型产品硬拼，而应把个人决策模型、执行反馈和透明自治做深。

## 5. 值得建设的四个 AI 壁垒

### 5.1 个人时间模型：从偏好记录到结果校准

**用户痛点**：人经常低估任务时长、高估每日容量，也难以稳定识别自己在不同时间、地点和工作类型下
的真实表现。

**为什么需要 AI**：简单统计可以计算中位数和误差，但任务描述、项目语义、上下文切换、模糊标签和
稀疏样本需要语义归类与不确定性推断。正确方案是“确定性统计为证据，模型处理语义与解释”，
不是让模型凭聊天历史猜人格。

**用户体验**：

- 创建任务时给出“基于类似任务，建议 50 分钟”，并显示样本与置信度；
- 规划前提示“你过去两周周三的可用容量通常比设置少”；
- 用户可接受、改写、关闭某类学习，且能查看建议依据；
- 样本不足时明确说“不足以个性化”，退回用户默认值。

**所需数据与能力**：任务类型、估时、开始/完成/暂停片段、延期和跳过原因、计划时间、实际时间、
工作时段、可选精力反馈；语义分类、相似任务检索、统计校准、时间衰减、置信度和冷启动策略。

**自治等级**：默认 Observe/Suggest。它可以自动更新派生特征，但不能仅凭 Memory 自动移动时间。

**风险与 HITL**：行为数据敏感；不能推断健康、人格或绩效；用户声明的偏好优先于派生模式；
任何改变日历事实的动作继续走计划预览和审批。

**实现难度**：高。难点不是生成总结，而是采集可靠的执行证据、区分“忘记打卡”和“真的拖延”，
并对小样本保持克制。

**当前基础**：`Task.estimated_minutes/actual_started_at/completed_at`、Task/Event 版本、
`TimeMemoryAnalyzer` 的 7/30/180 天窗口、稳定模式和置信度。缺少执行片段、结束原因、估时校准和
面向决策的类型化输出。

**产品价值**：同一个排程算法因个人模型不同而产生真正不同的结果。这比增加一个通用大模型更难复制。

### 5.2 约束感知、可解释的目标到时间规划

**用户痛点**：任务清单不等于可执行计划。用户需要在截止时间、优先级、固定承诺、专注块、休息、
切换成本和现实容量之间做取舍。

**为什么需要 AI**：LLM 适合澄清模糊目标、拆解工作和解释取舍；确定性规划器/优化器适合时区、冲突、
容量、依赖和硬约束。必须采用混合架构，不能让 LLM 直接“算日历”。

**用户体验**：

- 用户给出目标或一组任务，系统先补问缺失的截止时间、粒度或不可移动约束；
- 生成可编辑的 `SchedulePlan` 预览，逐项展示“为何安排在这里”和“未能安排的原因”；
- 显示总需求分钟、真实可用分钟、缓冲和超载，不用一份看似完整的计划掩盖不可行；
- 应用前重验全部事实，变化后标记计划失效并给出差异，而不是静默覆盖。

**所需数据与能力**：结构化 Goal/Project/Task 关系、优先级、截止时间、预计时长、可拆分性、依赖、
固定/柔性标记、工作时段、锁定块、外部日历 busy time、个人时间模型；意图澄清、任务分解、
约束求解、评分、解释和草案版本管理。

**自治等级**：Ask/Suggest 为主；应用计划至少需要一次明确确认。未来仅对用户预先授权的柔性块允许
低风险自动调整。

**风险与 HITL**：模型拆解可能改变用户目标；优化函数可能偏向“塞满”；外部参与者事件具有社会成本。
硬约束必须由后端验证，所有批量写入复用 ActionProposal，外部承诺永不默认自治。

**实现难度**：高。既要保证可行性，又要让方案稳定、可解释、不过度碎片化，还要在事实变化后安全失效。

**当前基础**：`PlanningService.find_free_slots()` 已正确处理工作时段、时区、DST、事件和计划任务占用；
`SchedulePlan` 和 `apply_schedule_plan()` 已提供草案、版本、用户写锁与 HITL 基础。当前 proposal 算法仍是
按 ID 的顺序贪心，需实质重构。

**产品价值**：把“我该做什么”落实到“我何时能完成”，并诚实暴露容量冲突，是时间 Agent 的核心兑现能力。

### 5.3 主动时间风险检测与注意力策略

**用户痛点**：用户往往在截止前才发现没有预留时间，在日程连续堆积后才意识到过载，或者让高价值任务
长期被紧急事务挤压。

**为什么需要 AI**：风险候选可由规则检测，但多项信号的语义归并、优先级解释和可行动建议需要模型；
同时，“是否值得此刻打扰”需要个体化的注意力决策，而不是固定阈值通知轰炸。

**用户体验**：

- 系统在“洞察收件箱”中汇总低紧急度事项；
- 对高置信、临近且可行动的风险发一次简短通知，例如“周五截止的任务尚缺 90 分钟，明天下午有空位”；
- 每条建议提供证据、影响、一个主操作和“稍后/不再提示这类”；
- 晚报/晨报聚合日常建议，避免每个检测器单独发通知。

**所需数据与能力**：截止时间、剩余估时、未来容量、冲突、连续高负载、反复延期、用户静默时段、
近期打扰次数、前台/后台状态和反馈；确定性 detector、候选去重、效用评分、注意力预算、文案生成与投递。

**自治等级**：Observe 自动运行；低紧急度 Aggregate；中风险 Suggest；高影响权衡 Ask。检测器不得直接写日历。

**风险与 HITL**：误报和通知疲劳会快速破坏信任。安全策略必须能在没有 LLM 时运行，设置每日上限、
冷却、过期、去重、安静时间和总开关。模型只负责归并/解释，不能越过通知配额和风险门槛。

**实现难度**：中高。检测规则本身不难，难的是评估“帮助价值减去打扰成本”并持续校准。

**当前基础**：Celery Beat、Briefing scheduler、`NotificationDelivery` 状态机、渠道 Provider、幂等、重试、
Android 本地通知、Web Push 和可观测性。缺少 `TemporalInsight`、注意力决策和反馈事件。

**产品价值**：让用户在问题仍可修复时得到帮助，同时比“全天候主动 Agent”更可信、更可控。

### 5.4 基于计划与现实差异的自适应重排

**用户痛点**：任何静态计划都会被延误、新会议、精力变化和临时任务打破；手工维护计划的成本最终让用户
放弃 time blocking。

**为什么需要 AI**：系统需理解变化含义、区分必须完成与可让步事项并解释新取舍；但冲突计算、候选生成、
版本验证和写入仍应确定性实现。

**用户体验**：

- 任务超时、跳过或新增冲突后，展示“计划与现实发生了什么变化”；
- 只重排受影响的柔性块，尽量保持其他安排稳定；
- 在变更预览中展示移动项、未安排项和代价；
- 用户可锁定事件/任务、撤回低风险变更，并逐类授权自动调整范围。

**所需数据与能力**：执行信号、计划版本、约束快照、影响图、锁定/柔性属性、稳定性成本、候选方案和
用户对历史建议的接受/修改/拒绝反馈。

**自治等级**：先 Suggest/Ask；获得明确策略授权后，才可对低风险、可逆、无外部参与者的柔性块 Execute。

**风险与 HITL**：频繁移动造成计划震荡；自动改变他人相关事件有社会风险；旧草案可能覆盖新事实。
必须设置移动次数、时间窗口、最小收益、稳定性惩罚、对象级授权和最终一致性重验。

**实现难度**：很高。它依赖前三个壁垒和足够评测数据，不应直接作为近期首发能力。

**当前基础**：事件/任务版本、用户级 schedule write lock、`SchedulePlan`、ActionProposal、
AgentRun interrupt/resume。缺少差异模型、约束快照、局部重排器和撤销语义。

**产品价值**：从“一次性生成计划”升级为“长期维护可执行计划”，是持续留存和高自治价值的来源。

## 6. 人机决策边界与自治梯度

### 6.1 自治等级

| 等级 | 含义 | 默认适用 |
| --- | --- | --- |
| L0 Observe | 读取事实、计算指标，不主动影响用户 | 统计、风险扫描、Memory 重建 |
| L1 Aggregate | 在用户已有入口聚合事实 | Today、晨报、晚报、洞察收件箱 |
| L2 Suggest | 给出带依据、可忽略的建议或草案 | 估时、优先级、空闲时间、计划、重排 |
| L3 Ask then Execute | 用户确认一次后执行一组明确变更 | 批量排程、创建/取消重要事项 |
| L4 Policy-authorized Execute | 在用户预先授权的窄范围自动执行，并可撤销/审计 | 未来的低风险柔性块移动 |
| L5 Broad Autonomy | 跨领域持续自主决策 | 当前不建设，也不作为默认目标 |

### 6.2 按操作划界

**可自动执行**：派生 Memory 重建、指标刷新、洞察候选过期、重复候选合并、计划草案失效、
确定性提醒派发和符合策略的消息聚合。这些操作不改变用户的时间承诺。

**应默认建议**：任务估时、优先级校准、工作块推荐、明日计划、空闲时间利用、风险提示和局部重排。

**应追问**：目标含义不清、截止时间缺失、硬约束冲突、多个方案代价接近、需要牺牲休息或已有承诺、
样本不足却会显著影响结果。

**必须明确确认**：批量写日历、取消任务/事件、覆盖用户计划、改变通知授权、向外部系统写入。

**不得默认自治**：删除不可恢复数据、邀请/取消他人、代表用户发送外部消息、移动有外部参与者的事件、
基于敏感推断采取行动、绕过权限/冲突/幂等/HITL。

自治升级必须是“按能力、按对象、按时间范围”的显式授权，不使用一个模糊的“自动模式”总开关。

## 7. 目标智能架构与 Intelligence Loop

### 7.1 总体架构

```text
PostgreSQL 业务事实 + 外部 Provider 快照 + 经同意的设备信号
                         |
                         v
              Temporal Context Snapshot
                         |
          +--------------+--------------+
          |                             |
          v                             v
  Deterministic Detectors       Personal Time Model
  冲突/容量/截止/变化             估时/负载/模式/置信度
          |                             |
          +--------------+--------------+
                         v
             Insight & Planning Services
         候选、约束、评分、草案、版本、证据
                         |
                         v
              Attention / Risk Policy
        suppress / digest / suggest / ask / approve
                         |
            +------------+------------+
            |                         |
            v                         v
      Time Steward / Briefing    Deterministic Jobs
      语义澄清、解释、交互        调度、过期、投递、重验
            |                         |
            +------------+------------+
                         v
           Web / Android / Notification Inbox
                         |
                         v
        接受、修改、拒绝、稍后、执行结果等反馈
                         |
                         +--------> 回到事实和派生模型
```

这不是新的多 Agent 网络。Time Steward 继续使用 `create_agent()` 处理开放式用户意图；外层 LangGraph
继续只做触发路由、Handoff、中断恢复和确定性 workflow；风险检测、规划求解、提醒投递和策略门控
由 Application Service/Celery 执行。

### 7.2 上下文分类

| 数据层 | 示例 | 权威与保留策略 | 消费方式 |
| --- | --- | --- | --- |
| 业务事实 | 事件、任务、提醒、计划、完成状态 | PostgreSQL 权威，按领域审计 | Service/Repository 查询 |
| 用户声明策略 | 工作时段、锁定项、安静时间、自治授权 | PostgreSQL 权威，版本化 | 硬约束或策略门控 |
| 外部事实 | 外部日历 busy time、天气、邮件中的承诺候选 | Provider DTO + 同步游标/来源；不得冒充本地事实 | 先归一化和标注来源 |
| 执行证据 | 开始、暂停、完成、跳过、稍后、建议反馈 | PostgreSQL 权威，最小化采集 | 模型校准与评测 |
| 派生特征 | 估时倍率、常见专注窗口、过载概率 | 可重建、有版本/样本/置信度/有效期 | 类型化 Decision Profile |
| 对话上下文 | 当前意图、最近消息、审批状态 | Checkpointer/对话存储，不代替业务事实 | 仅支持当前交互 |
| 设备上下文 | 前后台、通知动作、可选位置 | 明确授权、短期、最小化 | 仅用于投递时机和上下文，不做敏感推断 |

### 7.3 Memory 必须进入决策，而不只是进入 Prompt

当前 `TimeMemoryProfile` 已有行为窗口、规划风格、变化模式、稳定模式、置信度和时间衰减，这是好基础；
问题是它主要通过 `TimeMemoryMiddleware` 生成自然语言上下文，排程服务并不消费它。

未来应把 Memory 分成四类：

1. **声明偏好**：用户明确设定，保存在 PostgreSQL，优先级最高；
2. **事实统计**：可从事件/任务/执行信号确定性重算；
3. **决策特征**：带样本量、置信度、窗口和衰减的类型化特征，例如某类任务估时倍率；
4. **解释摘要**：供 Agent 和 UI 用的有限文本，不参与硬约束计算。

Planning/Attention Service 通过专门的 Application Service 获取只读 `DecisionProfileSnapshot`，
明确选择哪些特征参与评分。Agent 只能解释和询问，不能从 Memory 文本中自行派生隐藏规则。

需要坚持：

- Memory 仍可重建，业务事实仍在 PostgreSQL；
- 用户声明覆盖推断，低置信度不参与自动决策；
- 每个建议能回溯到事实和特征版本；
- 敏感对话、模型私有推理、API Key 和无关内容不得写入；
- 用户可查看、排除、重置和关闭学习。

### 7.4 触发模型

主动智能不等于持续调用大模型。建议采用三级触发：

1. **事件触发**：任务/事件/提醒变更、完成/跳过/延后、外部同步变化后，只运行廉价确定性 detector；
2. **定时触发**：晨间、晚间、每小时或每日扫描容量、截止和计划失效，生成/刷新洞察候选；
3. **用户触发**：聊天、Plan My Day、打开洞察、请求重排时，才进行更深的语义推理和方案生成。

仅当候选通过证据完整性、置信度、去重、风险和注意力门槛后，才调用 LLM 归并或生成解释。
这能降低成本、延迟和不可预测性，也符合现有 deterministic workflow 边界。

## 8. 主动 Agent 与注意力策略

### 8.1 主动工作流

```text
事实变化/定时扫描
  -> Detector 生成 TemporalInsight 候选
  -> 验证证据、版本、有效期与可行动性
  -> 合并同一问题，计算介入收益和打扰成本
  -> Attention Policy 选择 suppress / inbox / digest / notify / ask
  -> 必要时由模型生成基于证据的短解释
  -> NotificationDelivery 或应用内洞察收件箱
  -> 记录接受/修改/拒绝/稍后/关闭此类
  -> 更新策略统计和个人模型，不直接学习敏感结论
```

### 8.2 注意力评分因素

不能把评分交给模型自由决定。策略层至少考虑：

- **Importance**：关联任务优先级、目标价值、外部承诺；
- **Urgency**：距离截止或不可逆窗口还有多久；
- **Confidence**：事实是否完整，模型/规则置信度和样本量；
- **Actionability**：现在是否有明确且可执行的下一步；
- **Impact**：不处理可能造成的后果，以及建议能改善多少；
- **Disruption cost**：安静时间、会议中、近期通知次数、用户刚拒绝同类建议；
- **Freshness**：候选是否过期，事实是否在生成后变化。

### 8.3 强制策略

- 同类候选使用稳定 dedup key，变化不大时更新原洞察而不是重复发；
- 设置每渠道冷却、每日上限、安静时间、摘要窗口和自动过期；
- 低置信度只进收件箱，不发系统通知；
- 能在晨报/晚报处理的内容默认聚合，不即时打扰；
- 每次通知只有一个主要决策，复杂取舍回到 App 预览；
- 用户可选择“稍后”“不再提示这类”“总是允许此类低风险操作”；
- 模型失败时退回结构化模板，策略失败时默认不打扰；
- Android 设备状态只在权限允许、语义清楚时使用，不能从位置或使用行为推断健康/情绪。

### 8.4 晚报在该体系中的位置

晚报不是一个独立的“总结 Agent”，而是 L1 Aggregate 的固定入口：承载当天事实、计划与实际差异、
未完成事项、次日容量和少量高价值洞察，再把用户带到计划草案。具体内容、调度、降级和验收直接遵循
本文 Phase D 的主动智能边界。

## 9. 现有能力的取舍

### 9.1 保留并继续强化

- Django 模块化单体、PostgreSQL 权威、Application Service 写边界；
- `create_agent()` Time Steward 与只负责路由/HITL/workflow 的外层 LangGraph；
- `RuntimeContext.current_datetime` 的显式时间锚点和统一 UTC/IANA 时间基础；
- ActionProposal、interrupt/resume、版本控制、用户级 schedule write lock；
- Celery 确定性提醒和定时简报；
- Notification Provider、分渠道状态机、幂等、重试和审计；
- AgentRun/SSE/取消、模型与工具上限、fallback、结构化日志和 Prometheus 指标；
- Android 共用业务 UI、原生通知、安全 Token、更新验证；
- 外部数据 Provider 协议和 Time Memory 的可重建/可排除原则。

### 9.2 需要重构或升级

- `PlanningService.propose_schedule_plan()`：从顺序贪心升级为约束、评分、未安排原因和稳定性成本；
- `SchedulePlan`：增加约束快照、推荐理由、未安排项、有效期、失效原因和应用前全量重验；
- Time Memory：从 Prompt 摘要扩展为类型化、带置信度的决策特征服务；
- Briefing：从天气/新闻摘要转向时间决策摘要，支持晨报与晚报不同定义和调度；
- Notification：在 Delivery 之前增加 Attention Policy 和洞察聚合，不改变其可靠投递职责；
- Task：补充可拆分/锁定/精力或复杂度等规划属性，并用执行片段而非单一开始/完成时间计算实际耗时；
- Integration：先完成外部日历只读同步和来源/删除/冲突语义，再谈跨系统写入。

### 9.3 真正需要新增

以下只是未来所需的领域概念，命名和持久化必须在实施 ADR 中确认，不能先建空表：

- `ExecutionSignal/WorkSession`：记录用户明确产生的开始、暂停、继续、完成、跳过等最小执行证据；
- `TemporalInsight`：保存 detector 结果、证据引用、严重度、置信度、有效期、dedup key、处置和反馈；
- `DecisionProfileSnapshot`：Time Memory 面向决策服务的类型化只读快照，可先作为 schema/service，
  不必独立成业务表；
- Goal/Project/Task 的结构化关系：在规划智能验证后再引入，避免先造一个空洞目标管理器；
- 对象级 Automation Policy：仅在存在真实低风险自动化需求时持久化。

### 9.4 降低优先级

- 继续扩充通用 CRUD Tool 数量；
- 把新闻抓取做成产品中心；
- 大规模网页 RAG、通用知识库和向量数据库；
- 多 Agent 自组织、Planner/Reflection/Critic Agent 网络；
- 为未来规模提前拆微服务；
- 在没有执行数据和 benchmark 前做全自动日历重排；
- 在没有真实 Provider 数据和跨日历 benchmark 前设计复杂跨日历冲突优化。

## 10. 分阶段路线图

阶段之间是能力依赖，不是日期承诺。每一阶段都应有独立可用的产品结果和离线/在线验收。

### Phase A：事实与评测基础

**产品目标**：让系统知道“计划了什么”和“实际发生了什么”，并能客观判断规划建议是否更好。

**当前实施状态（2026-08-24）**：执行证据、只读同步基础和 benchmark baseline 已实现。`tasks` 领域新增不可变
`TaskExecutionSignal`、用户级幂等的 `TaskExecutionSignalService`、执行信号列表/写入/摘要 API，
任务完成 API 和 Time Steward 的完成 Tool 会记录 `completed` 信号；Web 任务页已提供开始/暂停操作。
`apps.integrations` 已保存连接状态、游标和错误，并按 `provider + account + calendar + event` 身份 upsert 外部事件；Web 日历显示
同步状态；确定性 Celery polling dispatcher 已按连接状态和 `next_sync_not_before` 选择有界批次，并对临时/限流错误做最多 3 次重试，对认证/永久错误 fail closed；`common.temporal_context.TemporalContextSnapshot` 已统一 Today 的显式 UTC/IANA 日边界。
`python manage.py benchmark_planning` 可重复输出当前 first-fit baseline。Android 已复用现有原生提醒、权限检查、离线幂等同步和点击深链，
并为任务提醒接入系统通知按钮式的“开始/跳过”动作，动作通过执行信号 API 幂等记录。详细边界见
[ADR 0022](../decisions/0022-task-execution-signals.md) 和 [ADR 0023](../decisions/0023-read-only-calendar-sync-foundation.md)。
新增只读 `IcsCalendarProvider` 与 `GoogleCalendarProvider`。Google Web OAuth 使用一次性 state 摘要、独立 Fernet 加密、
refresh 生命周期与 key 轮换；CalendarList/Events 有界分页，sync token 410 会在指定窗口做一次全量对账，全天/定时/
删除事件统一归一化，外部唯一身份包含 account/calendar。公共 Event API 不能伪造 Provider 身份，Nginx callback 不记录
含 code/state 的查询串。Web 日历已提供连接、当前范围同步和断开；Google 沙箱尚未实际运行，Microsoft/Outlook、
Webhook 和外部写回仍未实现。执行摘要现已比较计划 block、用户估时与实际投入，并在缺少执行证据时明确降级；Time Steward 可通过 Tool 查询执行摘要和脱敏同步状态。

- 用户体验：补充轻量开始/暂停/完成/跳过动作；展示估时与实际差异；用户可关闭行为学习。
- AI 能力：不增加高自治；建立冷启动、语义任务分类和估时 baseline。
- 后端：执行证据 Application Service、外部日历只读同步、统一 Temporal Context Snapshot。
- Agent：Time Steward 可查询执行差异和同步状态，但不自行推断未记录的实际行为。
- Memory：现有 schema 增加估时误差、样本量、来源和置信度；声明偏好与派生模式分离。
- Android：复用原生提醒、点击深链、通知按钮式开始/跳过和离线幂等同步；当前不后台持续追踪用户。
- 数据模型：评审 `WorkSession/ExecutionSignal`；为 Task 增加必要的规划语义时必须迁移和审计。
- API：执行信号、差异摘要和外部同步状态；变更后生成 OpenAPI 与前端类型。
- 前端：任务计时/状态反馈、数据与学习控制、同步错误可见。
- 风险：打卡负担、伪精确实际时长、外部日历重复/删除语义、敏感数据采集。
- 验收：事实链路可审计；重复上报幂等；时区/DST 正确；规划 benchmark baseline 可重复运行；
  没有执行证据时 UI 和 Agent 明确降级。

### Phase B：个人时间智能

**产品目标**：给出可验证、可解释的个体化估时、容量和工作窗口建议。

**当前实施状态（2026-08-24）**：已实现首个 `DecisionProfileService` 垂直切片。它把 `UserPreference`、30 天执行校准
和用户反馈组合为版本化 `duration_estimate` profile，暴露来源、样本量、置信度和 evidence；反馈通过
`TimeDecisionFeedback` 持久化并支持幂等、覆盖和关闭。新增 `benchmark_time_memory --user-id` 时序留出评测命令，可在样本不足时明确输出
`insufficient_data`。新增任务级 `/api/v1/time-memory/me/duration-recommendations/<task_id>/`：优先按用户明确填写的
project 或首个 tag 分组，其次使用版本化中英文确定性 taxonomy 生成语义 segment；分类器对不确定输入返回
`unclassified` / `ambiguous`，segment 至少 3 个执行样本才使用时间衰减后的中位倍率，否则回退版本化全局画像。建议返回
classifier/feature version、7 天 expiry、60 天半衰期、来源、样本量、校准后置信度和 fallback reason。评测同时输出固定
30 分钟、用户原始估时、全局校准、明确分组和语义分组候选的 MAE、calibration bins 及误差。容量风险与未来空闲时间 API 也已完成；Web/Capacitor 共用的规划工作台
会按所选范围展示后端返回的可用、已计划、未安排分钟数、风险等级和原因，不在前端重算容量规则。共用的任务页已按需展示
任务级建议、样本量、置信度和 evidence，并写入“准确/太短/太长/关闭”四类反馈；太短/太长只影响相同明确分组，Android 来源由同一页面标记，
不复制后端规则。Time Steward 已接入估时、容量和反馈 Tool；高置信 Decision Profile 也已作为版本化软输入进入 planner，低置信输入保持原估时。当前仓库仍没有足够真实执行样本证明留出集优于 baseline，真实校准曲线也未形成，因此 Phase B 的**内部实现已完成，数据验收保持 `NEEDS_DATA`**。
边界见 [ADR 0024](../decisions/0024-decision-profile.md) 和 [ADR 0027](../decisions/0027-free-time-recommendations.md)。

- 用户体验：显示建议值、依据、样本量与置信度；支持接受、覆盖和禁用某类建议。
- AI 能力：语义任务分类、相似任务估时、容量风险和个体校准；低样本回退全局/用户默认。
- 后端：`DecisionProfileService` 组合声明偏好、统计和派生特征，所有消费方读取版本化 snapshot。
- Agent：用类型化特征解释和追问，不从自由文本 Memory 生成硬规则。
- Memory：引入时间衰减、最小样本门槛、校准曲线和特征级排除/过期。
- Android：快速反馈“建议准确/太短/太长”，保持同一后端规则。
- 数据模型：优先复用 Time Memory schema/store；只有需要审计的用户声明和执行事实进入业务表。
- API：个人模型状态、建议依据、反馈和重置；绝不暴露敏感原始推理。
- 前端：个人规律页不做人格画像，只展示与时间决策直接相关的可纠正结论。
- 风险：确认偏差、样本偏差、把工作量等同绩效、隐私和模型漂移。
- 验收：在留出集上，个体化估时优于固定 30 分钟与用户原始估时 baseline；置信度与真实误差匹配；
  用户覆盖后立即生效且可追溯。

### Phase C：规划智能

**产品目标**：把一组任务稳定地转换成可执行、可解释、诚实暴露不可行性的计划草案。

**当前实施状态（2026-08-24）**：现有 `PlanningService` 已升级为确定性 planner v2：按优先级/截止时间稳定排序，逐任务
检查工作时间、已有占用、草案内冲突和 deadline，并把未安排项与 `reason_codes`、`plan_evidence` 一并保留；应用阶段只处理
已放置项并继续做版本校验；`/api/v1/planning/free-time-recommendations/` 已提供只读候选时间段与 reason codes；新增
`/api/v1/planning/plans/` 草案生成/查询和版本校验后的 apply API，形成可审阅的最小计划沙箱；`benchmark_planning` 现在同时输出 first-fit baseline 与 deterministic candidate 的对比结构，但这仍是离线候选算法比较，不代表线上 planner 已证明优于 baseline。
新增 `/planning` 工作台已提供 Plan My Day/Week、任务选择、范围设置、容量风险、机器可读未安排原因和一次确认应用；应用前会在用户级 schedule write lock 内重验批次内部重叠及最新事件/任务冲突。新增 compare API 同时生成“优先级/截止时间”与“长任务优先”两个确定性草案，并明确声明它们不是全局最优；regenerate API 在保留未选中草案块的前提下只重生成选中任务并递增草案版本，前端已可比较、切换和局部重生成。草案现保存 constraints/Decision Profile snapshot、TTL、版本、放弃/失效状态与原因，支持 edit/lock/validate/abandon；任务持久化 planning lock 和前后 buffer，buffer 会进入冲突复验。可拆分任务只在 `create_linked_event_blocks` 下生成满足 minimum chunk 的多个关联 Event。Time Steward 已接入生成、比较、验证、草案锁定/放弃和 HITL 应用 Tool。合成 benchmark 已报告两种算法硬约束违反数均为 0；真实数据的加权可行性、碎片化和交互延迟对比仍未完成，因此 Phase C 的**内部实现已完成，真实数据验收保持 `NEEDS_DATA`**。
边界见 [ADR 0025](../decisions/0025-deterministic-planner-v2.md)。

- 用户体验：Plan My Day/Week、容量条、锁定块、原因与未安排项、方案差异和一次确认应用。
- AI 能力：澄清目标、拆解过大任务、解释取舍；不负责冲突和时间运算。
- 后端：规划器 v2，区分硬/软约束，支持优先级、截止时间、可拆分、缓冲、个体特征和稳定性成本。
- Agent：调用规划服务生成方案；信息不足时追问；不能伪造“最优”。
- Memory：只将高置信决策特征作为软评分输入，记录使用的 snapshot 版本。
- Android：完整预览可在小屏审阅；批量变化按日期/影响分组，不塞入单条通知。
- 数据模型：扩展 `SchedulePlan` 的 constraints/evidence/unplaced/expires/invalidation；必要时引入 Goal 关系。
- API：生成、比较、编辑、验证、应用和放弃计划；应用保持事务、幂等、版本和 HITL。
- 前端：计划沙箱、冲突和取舍可视化、锁定/解锁、局部重新生成。
- 风险：计划过密、碎片化、旧计划覆盖新事实、算法偏好不透明、求解延迟。
- 验收：硬约束违反率为 0；每个未安排项有机器可读原因；应用前全量重验；相对当前贪心 baseline
  提高加权任务完成可行性且不过度增加移动/碎片；性能满足交互预算。

### Phase D：克制的主动智能

**产品目标**：在用户仍有修复空间时发现高价值风险，并用最小打扰促成决策。

**当前实施状态（2026-08-24）**：已实现 `apps.insights` 的确定性 detectors：扫描未来 48 小时截止或已逾期的未完成任务，并基于容量 forecast 发现未来两天容量风险，
写入带 severity/evidence/deduplication/expiry 的 `TemporalInsight`，并提供收件箱读取、snooze、dismiss、actioned API；Today
页面已展示未过期洞察，Briefing 页面提供不调用模型的确定性“今日收尾”预览；`AttentionPolicy` 已按用户开关、IANA 时区安静时间、
每日配额和同类冷却窗口生成可审计的 `STORE`/通知决策；确定性的 Celery 扫描入口会将获准决策幂等物化为 `NotificationDelivery`。当前尚未接入
真实供应商投递或模型晚报编辑；晚报偏好、定时生成和幂等系统通知已实现。新增
`evaluate_insight_guardrails` 读取既有洞察处置与投递事实，按显式观察窗口输出 action、dismiss、expired、sent、failed、false-positive 及比率；
guardrail 门槛未声明或没有投递样本时不会宣称通过。Today 之外已新增独立 `/insights/:insightId` 收件箱、历史 detail API、通知 deep link、单一处理入口和带 insight id/title 的聊天继续入口；Time Steward 通过 list/get/act Tool 读取证据并只在用户明确要求时处置。Today 支持显式“标记为不准确”和“关闭此类洞察”：后者写入用户偏好，随后同类洞察不再展示或物化，
仍处于 pending/queued/failed 的关联通知会经 `NotificationService` 状态机取消；误报率以窗口内生成洞察数为分母，使仅在收件箱出现的反馈也进入质量统计。生产升级扫描曾因旧 deep-link payload、变化的剩余小时正文与重算决策时间复用同一幂等键而被 Notification Service 拒绝；现已保留首次检测/未变化决策时间锚点，以版本化 key 生成新投递，并按 insight source/channel 将已物化投递视为不可变事实，升级兼容和重复扫描回归已覆盖。
真实供应商投递与观察窗口仍未验证，Phase D 的**内部实现已完成，外部投递与行为指标验收保持 `NOT_VERIFIED`**。
边界见 [ADR 0026](../decisions/0026-temporal-insight-inbox.md)。

- 用户体验：洞察收件箱、晨报/晚报、单一主操作、稍后/关闭此类和通知理由。
- AI 能力：归并候选、解释影响、生成行动选项；Detector 和 Attention Policy 仍确定性可测。
- 后端：`TemporalInsightService`、detector registry、dedup/expiry、Attention Policy、反馈采集。
- Agent：用户打开洞察后可继续对话；定时洞察不先调用 Time Steward。
- Memory：用接受/修改/拒绝反馈调整展示和门槛，不把“拒绝一次”永久固化为人格偏好。
- Android：可靠 deep link 到具体洞察/计划；支持通知 action；遵守 OS 权限和安静时间。
- 数据模型：洞察证据、状态、处置、投递决策和反馈；NotificationDelivery 继续只负责投递事实。
- API：洞察列表/处置、注意力偏好、摘要预览；所有服务端风险判断由后端给出。
- 前端：Today 中的轻量洞察区和独立收件箱；避免弹窗驱动的焦虑体验。
- 风险：误报、通知疲劳、过期建议、生成文案夸大风险、后台成本。
- 验收：通知配额和静默策略 100% 生效；过期/重复洞察不投递；高价值建议的接受/行动率提升；
  同类关闭率、通知禁用率和误报反馈不劣化到预设 guardrail。

### Phase E：受控的自适应 Agent

**当前实施状态（2026-08-24）**：已实现首个只读 `AdaptivePlanningService.preview_local_replan` 垂直切片。
它要求调用方显式提供可移动任务 ID，针对被阻塞区间生成局部移动/无法安排结果，并保留前后时间和 reason codes；服务不直接写入任务事实。
`/api/v1/planning/plans/local-replan-preview/` 已提供只读预览 API，`/api/v1/planning/automation-policies/` 已持久化显式的移动授权边界。
已实现变更批次前后快照与受版本保护的撤销 API；新增幂等的 `local-replan-apply` API，只允许显式授权且
`requires_approval=false` 的策略执行，并在写入前重验任务版本、批次内重叠和最新日程冲突；规划工作台已接入预览、执行和撤销。
要求审批的策略会拒绝 API 直写；Time Steward 已通过 `list_automation_policies` 与高风险 `apply_local_replan` Tool 接入既有
ActionProposal/HITL 中断、审批和同线程恢复链路。预览现直接返回 moved count、总/最大移动分钟和 unplaced count；
`benchmark_adaptive_planning` 用固定合成场景对照受限局部修复与全量压缩 baseline，并明确不把夹具结果当作产品收益。
本地多任务写入任一步失败会由数据库事务整体回滚，已有故障注入测试证明不会留下部分任务或半成品批次。新增确定性
`detect_disruptions` 比较计划任务与非取消 Event 的真实重叠，返回任务/事件、精确影响区间、重叠分钟和 reason code；规划页按影响时间线展示并自动填入局部重排输入。Automation Policy 已支持 PATCH 暂停/恢复、move cap 和 ownership 校验后的 Task allowlist 更新，不删除历史批次；确定性 Celery dispatcher 只消费启用、免审批且 allowlist 非空的策略，以 task version/event/overlap 派生幂等 operation id，并严格受 move cap 限制。Time Memory 从既有 `ScheduleChange` 派生接受、撤销、再次修改和移动距离统计，但这些统计不会扩大授权范围。Time Steward 可先检测扰动，再通过既有高风险 Tool/HITL 执行。外部日历写回、Provider 补偿和真实扰动数据仍未完成，因此 Phase E 的**本地受控闭环已完成，Provider/真实数据验收保持 `PARTIAL`**。

**产品目标**：计划被打破后自动发现影响，提出最小变化方案；只在用户授权的窄范围内自动维护柔性时间。

- 用户体验：变化时间线、局部重排预览、锁定、撤销、对象级自动化策略和清楚的“为何移动”。
- AI 能力：识别变化含义、比较方案和解释代价；可选反思只针对方案质量，不新增常驻 Reflection Agent。
- 后端：影响分析、局部重排、稳定性惩罚、策略授权、可逆变更和失败补偿。
- Agent：复杂权衡回到 Time Steward 追问；简单授权动作由确定性 workflow 执行。
- Memory：学习用户对建议的修改模式，但自治门槛由明确策略与置信度共同控制。
- Android：即时展示自动变更和撤销入口；离线时不得产生无法校验的自动写入。
- 数据模型：Automation Policy、变更批次、前后快照和撤销记录；避免复制既有审计事实。
- API：预览/授权/执行/撤销/暂停自动化；外部写入还需 Provider 能力与幂等语义。
- 前端：按影响而非按数据库对象展示变更；让用户看见保留了哪些稳定安排。
- 风险：计划震荡、社会性日程误改、Provider 最终一致性、撤销失败和信任损失。
- 验收：只移动授权的柔性对象；每次变更可解释、可审计、可撤销或有补偿；重排次数与移动距离受限；
  相比全量重排 baseline 明显降低计划扰动，同时保持截止可行性。

## 11. Now / Next / Later / Don't Build Yet

下面的 1 至 5 分是产品判断，不是实验结果：价值/必要性/差异化/可行性/数据就绪度越高越好，
成本/风险越高表示代价越大。它用于排序，不应写成对外指标。

| 优先级 | 事项 | 用户价值 | AI 必要性 | 差异化 | 可行性 | 数据就绪 | 成本 | 风险 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Now | 规划 v1 benchmark 与失败原因体系 | 4 | 2 | 3 | 5 | 4 | 2 | 1 |
| Now | 执行信号与计划/实际差异 | 5 | 3 | 5 | 4 | 2 | 3 | 3 |
| Now | 外部日历只读同步 | 5 | 1 | 2 | 3 | 1 | 4 | 3 |
| Now | 晚报作为事实复盘与明日规划入口 | 4 | 2 | 3 | 4 | 4 | 3 | 2 |
| Next | 类型化个人时间模型与估时校准 | 5 | 5 | 5 | 3 | 2 | 4 | 4 |
| Next | SchedulePlan/规划器 v2 | 5 | 4 | 5 | 3 | 3 | 4 | 4 |
| Next | 洞察候选与应用内收件箱 | 4 | 3 | 4 | 4 | 3 | 3 | 3 |
| Later | 注意力策略驱动的主动通知 | 5 | 4 | 5 | 3 | 2 | 4 | 5 |
| Later | Goal -> Project -> Task -> Time 对齐 | 5 | 5 | 5 | 2 | 1 | 5 | 4 |
| Later | 局部自适应重排 | 5 | 4 | 5 | 2 | 1 | 5 | 5 |
| Later | 对象级低风险自动化 | 4 | 3 | 5 | 2 | 1 | 5 | 5 |
| Don't Build Yet | 多 Agent 自组织网络 | 2 | 2 | 2 | 2 | 1 | 5 | 5 |
| Don't Build Yet | 通用网页 RAG/向量库 | 2 | 2 | 1 | 3 | 1 | 4 | 4 |
| Don't Build Yet | 全自动外部日历改写 | 4 | 2 | 3 | 1 | 1 | 5 | 5 |
| Don't Build Yet | 为规模提前拆微服务 | 1 | 1 | 1 | 2 | 5 | 5 | 4 |

执行顺序上，外部日历只读同步虽然 AI 必要性低，但它决定“真实承诺”是否完整，应早于高级排程；
执行信号虽然数据尚未就绪，却是个人模型和自适应能力的前置条件，也应优先建设。

## 12. 对当前架构的具体改动映射

### 12.1 `apps/tasks`

- 复用现有状态机、版本和 Service；不要让 Agent Tool 直接写执行数据。
- `actual_started_at` 可保留为首次开始时间，但不能把 `completed_at - actual_started_at` 直接当实际工时；
  需要明确的 session/signal 语义。
- 规划属性要区分硬事实与建议：用户锁定、可拆分、最晚完成属于结构化输入，模型分类属于派生特征。

### 12.2 `apps/planning`

- 保留 `find_free_slots()` 作为可行时间生成基础；扩展时继续覆盖半开区间、UTC/IANA 和 DST。
- 将 `propose_schedule_plan()` 拆成“构建约束快照 -> 生成候选 -> 评分/选择 -> 解释/未安排原因 -> 持久化草案”；
  是否拆类以实际复杂度决定，不能预建空优化框架。
- `apply_schedule_plan()` 在事务和写锁内重载全部事件/任务事实，验证计划内部冲突、外部新增占用、
  任务版本、计划有效期和策略授权。

### 12.3 `apps/time_memory`

- `TimeMemoryAnalyzer` 继续负责可重建统计，不直接成为业务事实写入者。
- 在 `schemas.py` 中逐步加入可供决策消费的类型化特征，保留 schema version、窗口、样本和置信度。
- 新的 Decision Profile 通过 Application Service 提供给 Planning/Attention，不允许这些模块解析 Prompt 文本。
- `middleware.py` 只注入解释所需的有限摘要，避免同一规则在 Agent 与 Service 中各实现一次。

### 12.4 `apps/briefings`

- Definition 与 Schedule 解耦，才能同时表达晨报、晚报和不同发送策略。
- 增加确定性“今日事实/差异/明日容量”section；天气和新闻是可选上下文，不是晚报主体。
- 定时入口继续直接进入 workflow；LLM 失败时输出结构化 fallback；不读取私密 Memory 文本。

### 12.5 `apps/notifications`

- `NotificationDelivery` 保持投递状态机，不承载“该不该打扰”的业务判断。
- Attention/Insight Service 在创建 Delivery 之前完成去重、配额、安静时间和渠道选择，并记录理由。
- Celery 重试只处理瞬时投递失败，不用重试重新做 AI 决策。

### 12.6 `apps/agents`

- 保留现有 Time Steward 单 Agent 和 Tool 分类；新增能力优先作为 Application Service + Tool 暴露。
- 新 trigger 如 `temporal_insight_due` 只有在真实 workflow 落地时加入，并由外层图确定性路由。
- 主动检测不应启动长对话 thread；只有用户进入交互或审批时才创建/恢复 AgentRun。
- 继续复用 Tool Policy、调用上限、Retry/Fallback、HITL、审计和 untrusted tool data 防护。

### 12.7 `apps/integrations` 与外部 Provider

- 第一阶段做 read-only calendar sync：账户/授权、游标、分页、增量变化、删除、时区、重复事件和来源映射。
- 外部事件可以参与 busy-time 计算，但必须保留 provider/source/external id 和同步新鲜度。
- Provider 不可用或数据过期时，规划结果显式降置信，不声称“日历完整”。
- 写回外部日历是独立高风险阶段，需要幂等、冲突、撤销/补偿和新的 ADR。

### 12.8 前端与 Android

- 继续通过 `frontend/src/api/client.ts` 和 feature API，前端只展示后端给出的风险、状态和原因。
- 新交互应围绕 Today、Plan Preview、Insight Inbox 和 Notification Deep Link，不再增加一个孤立 AI 页面。
- Android 适合承接即时反馈和低摩擦确认，但不应复制规划/注意力规则或长期后台采集。

### 12.9 运维与可观测性

- 为 detector 数量、洞察生成/抑制/投递、计划生成/失效/应用、建议反馈、模型调用成本建立低基数指标；
- Trace 关联 `request_id/operation_id/agent_run_id/plan_id/insight_id`，但不记录敏感上下文和模型私有推理；
- Celery 队列按提醒、简报/洞察、Memory/模型重任务隔离的必要性应先用队列延迟数据证明；
- 在线主动能力必须有 kill switch、用户级开关和全局速率限制。

## 13. 评测与 Benchmark 计划

### 13.1 当前已有

- 后端单元/集成测试覆盖时间、领域 Service、Agent routing/middleware/tool、HITL、Briefing、Notification、
  Time Memory 和 Planning；前端有 Vitest 与 Playwright 测试。
- `evaluate_time_steward` 使用真实模型评测 Tool trajectory，并记录成功、错误和延迟；当前数据集规模和
  运行结果以 `backend/apps/agents/evals/` 中的实际文件为准，不能外推成规划质量或用户价值。
- Prometheus 指标、`LLMCallAudit`、结构化日志和 Grafana/Loki/Alertmanager overlay 已提供运行观测基础。

### 13.2 必须补做的离线评测

**规划器 benchmark**：

- 数据集：合成边界用例 + 去标识化/用户自愿导出的真实周计划；覆盖 DST、跨日、紧截止、超容量、
  新增冲突、锁定块、可拆分任务和外部数据过期。
- Baseline：当前按 ID 贪心、Earliest Deadline First、Priority First、用户手工原计划。
- 指标：硬约束违反率、加权按期可完成率、安排率、未安排原因准确率、碎片数、上下文切换数、
  移动距离/次数、容量利用率、计划生成 p50/p95、应用前冲突检出率。
- 方法：固定 clock/timezone/seed；同一输入运行所有 baseline；硬约束先作为 gate，再比较软目标。

**个人模型 benchmark**：

- Baseline：固定 30 分钟、用户原估时、任务类型全局中位数、用户历史中位数。
- 指标：MAE、Median Absolute Error、分桶 MAPE、过短估计率、置信度校准误差、冷启动覆盖率；
  不能只报平均误差。
- 切分：严格按时间做 train/test，避免未来信息泄漏；按用户和任务类型分层报告，小样本单列。

**主动洞察 benchmark**：

- 建立有证据标注的场景集：真正过载、伪冲突、无行动空间、重复风险、已过期和不应打扰；
- 指标：detector precision/recall、去重准确率、过期建议率、可行动率、严重度校准、单次扫描成本和延迟；
- 文案评测只判断事实一致、是否夸大、操作是否匹配，不用“看起来聪明”代替业务正确。

**Agent regression**：

- 增加澄清、拒绝越权、计划失效、Memory 冲突、Provider 过期和高风险审批 trajectory；
- 记录 Tool 选择、参数正确率、无依据断言率、重试/回退次数、Token、成本和 p50/p95；
- 模型升级必须与固定 baseline 对比，不能只跑一次成功示例。

### 13.3 必须补做的在线验证

- 建议接受率、修改后接受率、拒绝/稍后/关闭此类比例；
- 建议后在截止前完成率的变化，但需避免把相关性写成因果；
- 晚报打开率、进入计划草案率、草案应用率和次日回访；
- 每用户每日通知数、重复/过期通知率、通知权限关闭率、7/30 天同类建议疲劳；
- 自动/半自动变更的撤销率、人工修正率和支持事件；
- 规划后计划稳定性、实际完成与估时误差随时间是否改善。

在线实验应使用 feature flag、分阶段用户授权和 guardrail；高风险自治不以点击率作为唯一成功指标。

### 13.4 当前不能声称的数据

项目目前没有可证明的真实用户规模、长期留存、生产级并发上限、个人化估时提升、规划完成率提升、
主动建议准确率、通知疲劳阈值或自动重排收益。这些全部标记为**需要补测**，不得写入简历或产品宣传。

## 14. 主要 Trade-off

### 混合智能，而不是端到端 LLM

优势是时间数学、权限和写入可测可审计，模型可以专注语义与解释；代价是需要维护结构化约束、
规则和模型之间的清楚契约，功能开发比“一个 Prompt 完成所有事”更慢。

### 先采集执行证据，再承诺个性化

优势是个人模型可验证；代价是用户需要低摩擦反馈，产品必须处理缺失/噪声数据。不能为了快速上线
而用聊天语气伪装个性化。

### 先 Preview/HITL，再逐类授权自治

优势是建立信任并积累真实反馈；代价是早期自动化程度不如激进产品。对时间承诺这种高外部性领域，
这个代价合理。

### 模块化单体，而不是微服务/多 Agent

当前数据规模与团队阶段下，单体事务和 Service 边界更容易保证一致性；代价是后台重任务需要认真隔离
队列和资源。只有监控证明独立扩缩容或故障隔离必要时，才改变部署拓扑。

### 外部日历先只读

只读先解决事实完整性并降低写入风险；代价是早期仍要用户在本地应用计划。写回能力应在同步、冲突、
幂等和补偿经过验证后再开放。

## 15. 最值得立即推进的三个验证

1. **建立 Planning Benchmark**：把当前 `propose_schedule_plan()` 固化为 baseline，先证明什么叫更好的计划，
   再替换算法。
2. **设计最小执行反馈**：用开始/暂停/完成/跳过和建议反馈获得可校准数据，验证用户是否愿意低成本记录。
3. **把晚报做成决策入口**：只基于确定性事实呈现计划/实际差异、未完成事项和次日容量，连接到
   `SchedulePlan` 预览，验证用户是否真的因此完成第二天规划。

这三个验证能同时回答最关键的问题：系统是否拥有足够真实数据、建议是否优于简单 baseline、
用户是否愿意把决策权逐步交给它。答案成立后，再建设主动通知和自适应重排才有依据。

## 16. 成功标准

Time Agent 的成功不应定义为“Agent 调用了更多 Tool”或“生成了更长的报告”，而应定义为：

- 用户更少漏掉真正重要的时间承诺；
- 计划更现实，无法完成的工作更早暴露；
- 变化发生后，恢复可执行计划所需的人工成本下降；
- 系统对个人的估时和容量判断随真实反馈改善；
- 主动介入足够少，但在出现时有清楚证据和可行动价值；
- 用户始终知道系统为什么建议、将改什么、如何拒绝或撤销。

最终产品形态不是一个替用户“管理人生”的自治黑箱，而是一个越来越了解用户时间现实、
能承担繁琐维护、又把价值判断和高风险承诺留给用户的长期协作者。

## 17. 工程实施规范与验收标准（Engineering Contract）

本节是后续 Phase、Feature、AI Capability、Agent Workflow 和架构调整的强制工程契约。
它用于防止“只有 Prompt、只有接口、只有 happy path、没有迁移/测试/评测、文档与代码不一致”
的伪完成。除非另有明确 ADR，以下规则与 [AGENTS.md](../../AGENTS.md)、现有 ADR 和项目规范一起生效。

### 17.1 Requirement Levels

- **MUST**：必须满足；否则 Feature 不得标记为 `COMPLETED`。
- **SHOULD**：原则上满足；未满足时必须记录原因、影响、Technical Debt 和后续计划。
- **MAY**：可选优化，不阻塞当前版本验收。

### 17.2 Feature Contract

任何非 trivial 修改开始编码前，必须在路线记录、Feature 文档或 ADR 中明确：

```text
Feature Name
Problem / User Scenario / Goal / Non-Goal
Input / Output / Trigger
Preconditions / State Changes / Failure Modes
AI Responsibility / Rule-System Responsibility / Human Responsibility
Data Required / Memory Required / Tools Required
Risk Level / Confirmation Policy
API Changes / Data Model Changes / Background Job Changes / Notification Changes
Acceptance Criteria
```

例如“任务时间分配”必须明确：输入任务、截止时间、估时、事件和偏好；LLM 只负责候选时间之间的
语义权衡；确定性系统负责冲突、截止时间、工作时间和最小持续时间校验；高影响排程由用户确认。

### 17.3 AI 与确定性系统边界

可以由可靠代码完成的冲突、截止时间、cooldown、权限和数据完整性检查不得交给 LLM。推荐链路为：

```text
LLM proposes -> Deterministic validation -> Policy check -> Human confirmation -> Execution
```

LLM 不得直接修改核心 Calendar、Task 或外部事实；低风险自动动作也必须有审计、撤销或幂等边界。

### 17.4 Agent 风险等级与可追踪性

- **L0**：只读查询、今日总结、负荷分析，可自动执行。
- **L1**：可撤销的低影响动作，如普通提醒、内部 metadata 或 planning proposal，必须可追踪。
- **L2**：用户日程修改、移动 block、重新排程，默认 `Suggest -> Confirm -> Execute`。
- **L3**：删除重要日程、取消重要任务、大规模重排、对外发送，必须显式确认。

重要 Agent 行为必须保存结构化 Decision Trace：`trigger`、`input_context`、相关 Memory、policy decision、
tool calls、action proposal、validation result、execution result 和 timestamp。不得保存模型私有推理或完整
Chain of Thought；可保存 reason codes、confidence 和引用的事实。

### 17.5 Prompt、结构化输出与 Context

影响行为的 Prompt 必须独立管理并版本化，至少记录 `prompt_name`、`prompt_version`、用途、输入变量、
预期输出和更新时间；重要 Prompt 改动必须重跑对应 evaluation。Agent 与业务系统之间优先使用 JSON Schema、
Pydantic、TypedDict、structured output 和 enum，不用自由文本或正则解析驱动写入。

每个 Agent 必须声明 Required Context、Optional Context、Retrieved Memory 和最大 Context Budget；不得把半年
聊天记录无界注入 Prompt，只检索当前决策所需信息。

### 17.6 数据模型与 API

数据库修改必须有可执行 migration，并说明现有数据、nullable/default、index、relationship、向后兼容和回滚策略。
API 变更必须定义 Method、Path、认证、请求/响应 schema、错误码、副作用、幂等性和权限；输入必须校验，不能
把含义模糊的内部异常直接暴露为 500。Mutation 尤其要考虑重复请求、后台重入和 Agent action 幂等。

### 17.7 Scheduler、Notification 与 Memory

后台任务必须明确 Trigger、Frequency、Input、Output、Retry、Timeout、Idempotency、重复保护、失败处理和可观测性。
提醒和主动通知不得由 Agent 直接投递，必须经过 `Insight -> Importance -> Urgency -> Interruption Policy -> Channel`，
并支持 cooldown、去重、频率上限、静默时段和优先级。

长期 Memory 不是 Agent 日志库。只有稳定、可复用、影响未来决策且证据足够的信息才能写入；应尽量记录
`content`、`category`、`confidence`、`evidence`、`first_observed`、`last_updated`、`observation_count` 和 `decay`。
每类 Memory 都必须能说明它影响哪个 scheduling、planning、notification 或 workload decision。

### 17.8 Failure Path、降级、安全与观测

每个 Feature 必须同时定义 Happy Path 和 LLM timeout、Provider/API 不可用、malformed output、Memory 不可用、
权限拒绝、数据库失败、进程被杀、scheduler 重启、网络断开、重复请求和 stale state 等 Failure Path。
AI 不可用时，查看、创建和本地提醒等核心时间管理仍必须可用；关键操作结果必须明确为 `SUCCESS`、`FAILED`、
`PARTIAL` 或 `REQUIRES_USER_ACTION`，禁止 silent failure。

新增重要能力至少关联 Request、Agent Run、Tool Call、LLM Call、Scheduler Job、Notification、Memory Update、
Error 和 Latency。日志不得记录 Token、密码、Authorization header、敏感内容或模型私有推理，只使用 request/user
标识、run/job/action、结果、延迟和 error code 等可关联字段。

### 17.9 测试、Eval 与验收

核心 Feature 至少需要 Unit Test 和 Integration Test；关键用户流程需要 E2E。重要 AI capability 还必须有固定
Evaluation Dataset，每条包含 input、context、expected behavior 和 forbidden behavior。AI Eval 验证 decision、
action、constraint、安全边界和 required fields，不要求逐字一致；Prompt、Memory、Tool、Policy 或 Planning 改动
必须重跑既有 Regression Suite。

Acceptance Criteria 必须可验证，并同时包含 Positive、Negative 和 Edge Cases，例如过期 deadline、duration 超出
可用时间、重叠事件、DST、跨日、全天事件、缺失估时和低置信偏好。不得用“AI 更智能”“体验良好”作为唯一验收。

### 17.10 Definition of Done

只有同时满足以下条件才可标记 `DONE`：Feature Contract、用户场景和 Non-Goal 明确；AI/Rule/Human 边界、风险、
数据模型、migration、API、核心逻辑、Failure Path、权限、安全、Logging/Observability 完成；Unit、Integration、
关键 E2E、AI Eval 和 Regression 通过；文档已更新；无临时 Mock、未说明 TODO、dead code 和已知 P0/P1 Bug；每条
Acceptance Criteria 都有证据。否则只能标记 `PLANNED`、`IN_PROGRESS`、`PARTIAL` 或 `BLOCKED`。

### 17.11 完成报告与兼容性

每次交付必须报告 Implementation Summary、Files Changed、Architecture/Data Model/API/Agent/Memory/Notification
Changes、Tests、Evaluation Results、Known Limitations、Technical Debt 和逐条 Acceptance Criteria Result（`PASS/FAIL`
及证据）。测试必须给出实际 Command、Result 和相关用例；无法运行必须标记 `NOT VERIFIED`。

修改已有模块时必须检查 Existing API、Database、Android App、Notifications、Tests 和 Agent Tools。重大 Agent、
Memory、Scheduler、通知、数据库或部署决策应创建简短 ADR；同时遵守“正确 -> 简单 -> 可观测 -> 可测试 -> 可扩展”，
不提前建设没有当前需求支撑的 event bus、微服务、向量数据库或大量 Agent。

### 17.12 AI 成本约束

每个新增 AI capability **SHOULD** 明确 `LLM Call Frequency`、平均与最坏 Token 成本、触发频率、缓存可能性和
批处理可能性。不得设计“每分钟调用大模型扫描所有用户日程”一类无界轮询；优先采用：

```text
deterministic rule trigger -> candidate event -> LLM reasoning only when needed
```

没有真实调用数据时必须标记“需要补测”，不得用模型价目表推导并声称线上成本已经达标。

### 17.13 禁止 Fake Completion

以下任一情况都不得标记 `COMPLETED`：只有 placeholder 接口、只有 Mock、只有没有真实逻辑的 UI、只有 Prompt、
只有 happy path、只有未运行的测试、没有 migration 的 ORM 变更，或仍存在未披露的 TODO/临时代码。测试代码存在但
没有实际执行时，状态必须是 `UNVERIFIED`。功能部分可用但外部环境尚未验证时，应使用 `PARTIAL` 并列明缺口。

### 17.14 Rollback 与能力开关

高影响 Feature **SHOULD** 明确故障后的关闭或恢复方式。主动 Agent、自动重排、通知和自治执行优先提供 feature flag、
配置开关、capability switch 或可审计的撤销操作；不得让关闭一个实验性 AI 能力必须依赖数据库手工修复。涉及核心事实
的批量写入必须定义事务边界、部分失败语义和补偿方案。

### 17.15 Phase Acceptance Gate 与 Exit Criteria

Roadmap Phase 不能因为代码写完就结束，必须同时通过：

```text
Product Gate -> Engineering Gate -> AI Evaluation Gate -> Regression Gate -> Documentation Gate
```

- **Product Gate**：核心用户场景在目标环境真实可用。
- **Engineering Gate**：不是 Prototype，包含完整数据、服务、失败和权限链路。
- **AI Evaluation Gate**：涉及 AI 时达到预先声明的质量门槛；纯确定性能力注明 `NOT APPLICABLE`。
- **Regression Gate**：已有核心能力没有 P0/P1 回归。
- **Documentation Gate**：架构、API、数据模型、运行和限制与代码一致。

每个 Phase 必须有可验证 Exit Criteria。例如个人时间智能不能以“完成个人时间模型”为标准，而应验证偏好类别、
confidence/evidence、更新或衰减、决策使用、无 Memory 降级、硬约束优先级、固定 Eval 和回归结果。

### 17.16 指标与最小评测集

核心 AI 能力必须选择与风险匹配的指标：规划至少关注冲突、约束满足、deadline 满足、非法动作和用户拒绝；主动能力
至少关注有效通知、重复、false positive、频率和 dismiss；Memory 至少关注决策使用、错误与陈旧比例。指标定义、分母、
观察窗口和阈值必须在看结果前声明。

首阶段不追求研究级 Benchmark。每项核心 AI capability 先建设 20-50 个高质量固定场景，覆盖 normal、edge、
adversarial 和历史 regression；未达到样本量时继续如实记录现有数量，不得补造 case 或指标。

### 17.17 Bug Severity

- **P0**：数据丢失、严重安全问题、危险 Agent 动作或大规模错误修改 Calendar，阻塞发布。
- **P1**：核心功能不可用、严重错误排程、重复通知或重要 workflow 失败，阻塞 Phase 完成。
- **P2**：一般功能异常，可进入明确的 Technical Debt。
- **P3**：不阻塞核心阶段的 UI 或轻微问题。

### 17.18 文档与 Source of Truth

代码涉及 Architecture、API、Data Model、Agent、Memory、Scheduler 或 Notification 时必须同步更新对应文档。同一规则
尽量只有一个事实源：架构归架构文档、路线归本路线、Agent Policy 归策略/ADR、Memory 归 Memory 文档、API 归
OpenAPI；其他位置使用链接引用，避免复制后漂移。本节是 Phase A-E 及后续能力的工程验收事实源，`AGENTS.md` 是仓库
级不可违反的开发规则；冲突时应先修正文档或提交 ADR，不得静默选择较宽松的版本。

### 17.19 Coding Agent 工作流与范围控制

较大任务统一采用：

```text
Inspect -> Understand -> Identify Constraints -> Define Acceptance Criteria -> Design
-> Implement Minimum Complete Solution -> Test -> Evaluate -> Regression Check
-> Update Documentation -> Self Review -> Report Evidence
```

变更遵循 `smallest coherent change`。发现不阻塞当前 Feature 的重大重构需求时，只记录 Observed Problem、Impact、
Recommended Refactor 和 Whether Blocking；不得顺手扩大范围。

### 17.20 Self Review

完成前必须逐项检查：Acceptance Criteria 是否全部满足；既有约束是否被削弱；AI 能否绕过确定性校验；动作能否重复
执行；LLM、网络、数据库、进程重启和 stale state 失败时会怎样；Memory 错误是否越过硬约束；通知是否打扰；是否会
意外修改用户数据；测试是否真实执行；文档是否与代码一致。发现问题必须修复或在完成报告中明确记录。

### 17.21 最终工程原则

1. **AI proposes, system validates.**
2. **High-impact actions require trust and confirmation.**
3. **Memory exists to improve decisions, not to collect information.**
4. **Proactivity must compete for user attention.**
5. **AI failure must not break basic time management.**
6. **Every important AI behavior must be evaluable.**
7. **Every important action must be traceable.**
8. **Prefer deterministic logic whenever deterministic logic is sufficient.**
9. **A feature without tests and acceptance evidence is not finished.**
10. **不以 AI Feature 数量为目标，以 Time Agent intelligence loop 的质量为目标。**

### 17.22 最终完成声明

任何任务结束时必须按以下结构给出证据，不能只写 `Done`：

```text
STATUS: COMPLETE / PARTIAL / BLOCKED / UNVERIFIED
IMPLEMENTED: ...
TESTED: ...
EVALUATED: ...
ACCEPTANCE: ...
NOT COMPLETED: ...
KNOWN RISKS: ...
NEXT RECOMMENDED STEP: ...
```

只有实现完成、测试实际运行、Acceptance Criteria 全部满足且没有阻塞级缺陷时，才能使用 `STATUS: COMPLETE`。

## 18. Phase A-E 按 Engineering Contract 的审查结果

### 已通过（PASS）

| 条目 | 证据 |
|---|---|
| 数据模型与 migration | `TaskExecutionSignal`、`CalendarSyncConnection` 及对应 migration；`makemigrations --check --dry-run` 无变更 |
| Tool -> Service -> ORM | `complete_task` 与执行信号 API 均经 `TaskExecutionSignalService`；日历同步通过 `CalendarSyncService` |
| 幂等、权限、UTC/IANA | 用户级 idempotency key、用户 ownership 查询、`to_utc`、显式时区校验与 `TemporalContextSnapshot` |
| 失败处理与可审计性 | Provider 错误写入连接状态；执行信号有 source/metadata；事件同步复用事件审计 |
| 结构化 API 契约 | OpenAPI 与 `frontend/src/api/generated/schema.d.ts` 已重新生成 |
| Unit/Integration/Regression | 后端全套测试在 SQLite 与独立 PostgreSQL 17 均通过；前端 Vitest、fixture Playwright 与一条显式启用的真实后端 Phase A-E 浏览器链路通过；ruff、严格 mypy、前端 lint/build、Django check 通过。实际最终计数见下方本机评测记录 |
| 可重复 benchmark | `benchmark_planning` 固定输入、固定 seed/时间，当前 first-fit baseline 可重复输出 |

### 当前只能标记 PARTIAL

| 条目 | 当前状态与影响 | 后续计划 |
|---|---|---|
| Feature Contract 文档 | 已补充 [Phase A-E Feature Contracts](feature-contracts-phase-a-e.md)，覆盖执行证据、Google OAuth 只读同步、规划、洞察和局部重排的输入/边界/失败/验收 | 后续新增 Microsoft、Webhook 或外部写回时继续拆分独立 contract |
| E2E 验收 | fixture 场景之外，`real-backend.spec.ts` 已在一次性 PostgreSQL 17、Redis 7、当前源码 Uvicorn 与 Vite 上完成登录、任务执行、估时反馈、计划应用、洞察关闭、局部重排和撤销，全程未注册 API route mock | 将同一显式 opt-in 用例接入 release gate，并保存失败时 trace；生产拓扑与真实 Google OAuth 沙箱仍另行验收 |
| Android 通知动作 | 已接入任务提醒 action type、开始/跳过 API 调用和任务页深链；`1.1.7 / 11` release APK 已通过 `testDebugUnitTest`、`lintDebug`、签名、zipalign 和公网回下载完整性验证并正式发布；更新器同时校验版本 code/name，并以版本与哈希生成唯一安装 URI；ADB 未发现已连接设备，因此仍缺 native 运行证据 | 在 Android 真机/模拟器上验证升级、进程被杀、重复点击、离线恢复和失败反馈 |
| 外部 Provider | Google 只读 OAuth、独立加密/轮换、分页、增量游标、410 对账、tombstone、多日历身份、有界 Celery 轮询、错误脱敏和 Web 控制已实现并有 fake-transport/API/migration tests；`verify_google_calendar` 可输出不含账号、calendar ID、URL、游标或 Token 的版本化报告并在失败时返回非零；未使用 Google 沙箱实际授权、撤权或长时间增量同步 | 用专用 Google 沙箱账号执行首次授权、分页、更新、删除、410、429/撤权并分别保存脱敏报告；Microsoft、Webhook 和写回另立 Feature Contract |
| 计划/实际完整对比 | 执行摘要 API/UI 已显示计划 block、估时与实际投入偏差，并对无证据状态降级；尚未证明这些数据驱动的 planner 改进优于 baseline | 收集真实样本并运行时序留出 benchmark，评测算法改进 |
| AI Eval / Decision Trace | Phase A 新增部分是确定性基础设施，未引入新的 LLM capability；现有 Time Steward eval 未因这些基础字段改变而扩展 | 在 Planning/Insight Agent 开始前补固定 dataset、reason codes、policy/validation trace 和 regression cases |

因此，Phase A 的**事实与评测基础实现可标记 PASS**；若把“完整 Phase A 产品体验”定义为包含 Android 系统通知动作、真实 Google OAuth 沙箱验收、生产拓扑 E2E 和完整计划/实际视图，则整体状态应保持 `PARTIAL`，不能写成全部能力已完成。

### 2026-08-24 本机评测记录

- 默认 SQLite 与全新一次性 PostgreSQL 17 的后端全量回归均为 `474 passed, 3 skipped`；PostgreSQL 验收先在空库执行全部 Django migration 和 `setup_langgraph`，再由 pytest 创建独立测试库运行当前全套用例，结束后删除容器，全程未连接生产数据库。前端 Vitest 为 26 个文件、`107 passed`，当前 fixture Playwright 为 `27 passed, 1 skipped`；隔离真实后端 Phase A-E 用例以当前源码单独为 `1 passed`。Ruff、严格 mypy（379 个源文件）、ESLint、Django security/system check、migration drift、OpenAPI 类型生成和生产构建通过；当前只读挂载项目配置的 `time-agent-nginx-1` 也已通过真实 `nginx -t`。`1.1.7 / 11` 已部署到当前生产 Compose，生产 migration plan 为空，公网 APK 回下载的 manifest、大小、SHA-256 与签名复核通过。
- `python manage.py benchmark_planning`：固定 4 个 case、11 个任务；first-fit baseline 安排 7 个任务、390 分钟，placement ratio `0.6364`；longest-first best-fit candidate 安排 8 个任务、480 分钟，placement ratio `0.7273`。差异来自新增的固定“长短槽错配”反例，只证明候选算法在该合成 case 上避免了短任务占用唯一长槽，不能作为线上 planner v2 的产品收益。
- 两个规划算法在固定 4 个 case 中报告的硬约束违反数均为 `0`；这是合成输入下的实现回归证据，不是实际日历的违反率。
- `python manage.py benchmark_adaptive_planning`：固定 1 个变化场景；受限局部重排移动 1 项、总位移 60 分钟，full-compaction baseline 移动 3 项、总位移 480 分钟；两者 deadline/overlap 违反数均为 `0`。该差异只验证稳定性指标和对照工具可运行，不能作为真实用户收益。
- `benchmark_time_memory` 需要真实用户 ID 和至少 10 个带完整执行区间的样本；隔离数据库只含验收夹具，因此未运行产品数据评测，状态为“需要补测”，不得引用测试夹具中的 MAE。
- `evaluate_insight_guardrails` 已能计算显式窗口内的 action/dismiss/delivery failure/false-positive 指标并执行调用方预先声明的门槛；当前没有真实观察窗口，状态为“需要补测/补采集”。
- 独立 PostgreSQL 17 全量测试首次发现 SSE 轮询在事务内无条件清理连接会留下 psycopg `BAD` connection；修复为只清理非事务连接后全套通过。独立新库依次执行 Django migrate、既有 `setup_langgraph` 部署步骤和真实浏览器写链路；该结果证明数据库与 HTTP 契约可运行，不代表生产规模、延迟或长期稳定性。
- 仍需补充：真实时序留出集上的分层 MAE/校准误差、真实规划集的硬约束/加权可行性/碎片化/延迟、真实变化集的扰动距离与截止可行性，以及真实通知观察窗口。

## 19. Phase A-E 外部验收矩阵

下表只列无法由当前仓库和本机夹具替代的证据。没有实际报告或原始结果时一律保持 `NOT VERIFIED`。

| Phase | 验收环境与步骤 | 必须保存的证据 | 当前状态 |
|---|---|---|---|
| A / Android | Android 24、27 和当前主流版本至少各一台真机或模拟器；按 [Android 构建与验证指南](../android-build-and-verify.md) 测进程被杀、重复点击、离线重放、重启重排和失败反馈 | 设备/系统版本、APK SHA-256、步骤结果、adb 日志和失败截图 | `NOT VERIFIED`：当前 ADB 无设备 |
| A / Calendar | Google OAuth 沙箱账号；完成首次同步、分页、更新、删除、游标过期、限流和撤权 | 运行 `verify_google_calendar` 保存版本化脱敏报告、同步计数、分页/HTTP 状态计数、错误状态和游标重置结果；不得保存账号、calendar ID、URL、游标或 token | `IMPLEMENTED / NOT VERIFIED`：Google 只读 OAuth、contract tests 与脱敏报告命令已完成，尚无真实 Google 沙箱报告；ICS 私有 feed URL 仍是明文连接标识 |
| A-E / E2E | 从空库启动隔离 PostgreSQL/Redis/当前源码 Django/Vite；执行任务动作、估时反馈、计划应用、洞察处置、局部重排与撤销 | 可重复的 opt-in Playwright spec、后端状态与数据库事实；发布 gate 保存 trace | `PASS (LOCAL ISOLATED)`：`real-backend.spec.ts` 无 route mock 通过；未把结果外推为生产拓扑、并发或 Provider 验证 |
| B / Duration | 单用户至少达到命令最小样本门槛后运行 `benchmark_time_memory --user-id <id>`，按完成时间做时序留出 | 样本数、train/test 划分、fixed-30/user-estimate/global/stratified MAE、confidence calibration error、分组回退数、运行时间与代码版本 | `NEEDS DATA`：分层与校准输出已实现；当前没有达到门槛的真实执行样本，且不得用夹具冒充 |
| C / Planning | 脱敏真实任务/日历集回放 baseline 与 candidate；覆盖 DST、跨日、全天事件、截止期、碎片容量和不可行输入 | 硬约束违反率、placement、加权可行性、延迟、未安排 reason 覆盖率 | `PARTIAL`：4 个合成 case 可重复，真实集未跑 |
| D / Attention | 启用 live email/web-push 测试并运行一个预先声明的观察窗口 | 发送/失败/重试、接受/actioned、dismiss、false-positive、同类关闭和通知禁用数据；先声明 guardrail 再观察 | `NOT VERIFIED`：反馈与 guardrail 计算已实现，2 个 live notification 测试仍显式跳过 |
| E / Stability | 对同一变化输入比较局部重排与全量重排，并在 Provider 沙箱测试写回/补偿 | 移动任务数、总/最大移动分钟、截止可行性、撤销成功率、Provider 幂等与补偿 trace | `PARTIAL`：合成稳定性 benchmark 与本地事务回滚已通过；真实变化集和外部写回未实现 |

执行这些验收前不得把状态改为 PASS；失败结果也必须保留，因为它们决定下一轮优化优先级。
