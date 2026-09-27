# TimeAgent Agent Harness 排程能力演进实验

- 状态：本轮实验完成（未部署）
- 开始日期：2026-09-27（Asia/Shanghai）
- 仓库基线：`c57fcd648674d9de1f3dd07ac1f9de9b68425261`；工作区包含上一轮尚未提交、已部署的实现改动
- 研究要求：[`docs/optim/优化.md`](../optim/优化.md)
- 相关既有实测：[`timeagent-capability-and-scheduling-scenarios-2026-09-26.md`](../evaluation/timeagent-capability-and-scheduling-scenarios-2026-09-26.md)

## 0. 架构审计（实验前）

### 当前规划决策图

| 决策 | 当前实现 | 正确性类型 | LLM 适配性 | 推荐 Harness 方式 |
|---|---|---|---|---|
| 识别请求范围、选任务、提取用户目标 | Time Steward `create_agent()` + 自然语言提示 + 工具调用 | 语义决策 | 高 | 留在同一个 Agent 的工具循环 |
| 选择查询范围和事实 | Agent 选择 `get_planning_context`；Planning Service 从 PostgreSQL 读取任务、日历和偏好 | 事实必须可信 | 事实不可由模型造出；查询意图可由模型选 | 现有只读 Planning Tool；数据库继续作唯一权威 |
| 把任务名/描述里的阶段、先后关系和节奏转为决策 | `TaskScheduleDecision` 可表达软目标时间、硬时间窗、前置任务和最小间隔；由 Agent 填 Tool 参数 | 混合 | 高，尤其是阶段语义与偏好映射 | Pydantic Tool 参数 + 快照；缺信息时由 Agent 澄清 |
| 任务默认顺序 | `PlanningService._ordered_tasks` 按优先级/截止日或时长排序；依赖只表达硬先后 | 启发式 | 部分适合 | 保留确定性默认；明确节奏/阶段通过结构化意图进入 Harness |
| 空闲时段、工作时段、时区和 DST | `PlanningService.find_free_slots` | 硬正确性 | 不适合 | 确定性服务；不得交给 LLM 计算 |
| 多任务落位和拆分 | `_build_plan_items` 贪心分配；默认选最早可用段；拆分按任务 `splittable` 与最小块规则执行 | 启发式 + 硬约束 | 时段偏好、阶段分配适合；底层搜索不适合 | Agent 提供结构化软/硬意图，服务产生可行结果 |
| 容量评估 | `CapacityForecastService` 调用同一空闲时段计算；工作日默认已统一为周一至周五 | 确定性事实 | 不适合计算；适合权衡风险 | 服务返回证据，Agent 决定是否延后或询问 |
| 候选比较 | `compare_schedule_plans` 生成两种排序草案并进行确定性校验/指标计算 | 候选生成确定；偏好选择语义化 | 适合比较取舍 | 先验证候选，再由现有 Agent 根据用户目标解释；不另加 ranker |
| 创建、复核、过期与应用 | `SchedulePlan` 快照、创建校验、显式 validate、apply 时重验；写入在 Service 事务内 | 硬正确性/业务事实 | 不适合 | 继续由 Planning Service 和 HITL 强制执行 |
| 失败修复 | Agent 能观察 Tool 结果并再次调用工具；初始 propose 会附创建校验结果，但没有专用 repair schema/critic 阶段 | Harness 控制流 | 适合判断是否重试/调整或询问 | 使用同一 `create_agent()` 回环及现有调用上限；仅在失败用例证明必要时增加结构 |
| 记忆参与计划 | `TimeMemoryMiddleware` 注入已授权上下文；语义记忆由工具检索；Decision Profile 作为估时证据 | 软证据 | 适合由 Agent 权衡 | 只作软偏好，显式请求优先；不让 Planning Service 读取 Memory |
| 何时询问用户 | Prompt 与现有 Agent 最终决策；没有单独 Planning Clarification 状态 | 用户偏好/风险决策 | 高 | 留在 Harness；在回归集中覆盖欠缺关键偏好的情景 |

既有多用户端到端实测暴露了明确的长周期体验失败：四周训练被放在同一天，备考任务集中在最初几天，阶段顺序没有稳定反映到时间块。此前的 `test_llm_guided_schedule.py` 手动构造 `TaskScheduleDecision` 并直接调用 Planning Service，因此只能证明“服务能执行结构化意图”，不能证明真实 Agent 会从用户请求与任务语义中提取意图。

上一轮已统一工作日默认值、容量预测、生成和应用时校验，故本轮不把这一已完成修复计为 Harness 收益。当前工作区另已具备工具 Manifest、Pack 路由与动态 Tool Policy；它们是本轮 Harness 的基线，不重复加路由 Agent。

### LangChain / LangGraph 能力与版本

当前生产 Compose 镜像安装 LangChain `1.3.14`、LangGraph `1.2.9`。项目已经使用 `create_agent()`、typed Tool / `ToolRuntime`、动态 Prompt、中间件、MemoryMiddleware、Tool/Model 限额、retry/fallback、Human-in-the-loop、State、checkpointer/store、streaming 与 Outer Graph resume。无需升级依赖，也没有证据要求另造 Planner Agent、Planning Subgraph 或第二个运行时。

### 目标 Harness 架构

```text
自然语言目标 + RuntimeContext + MemoryMiddleware
                     ↓
           现有 Time Steward create_agent()
   理解任务阶段/顺序/软偏好，判断默认、修复或澄清
                     ↓
             Planning Tool（typed schema）
    context → 结构化 TaskScheduleDecision → proposal
                     ↓
            确定性 Planning Service
  数据事实 / 空档 / 约束 / 快照 / 版本 / 校验 / 事务
                     ↓
       Tool Observation（计划、未排原因、校验）
                     ↺ 同一 Agent 判断接受、修复或问用户
                     ↓
        apply_schedule_plan → ActionProposal / HITL
                     ↓
      Service 最终重验、原子应用、执行轨迹
```

Harness 状态仍使用现有 Agent 消息与 LangGraph State；可信身份、时区、时间锚点和权限留在 RuntimeContext；本轮决策进入 `SchedulePlan.constraints_snapshot`；跨轮记忆继续由 Middleware/Store 与 Memory Tools 提供；PostgreSQL 保存业务事实。Critique 的第一阶段由 Agent 在读取工具结果后的同一轮推理承担，确定性 metrics/validator 检查机器可精确判定的边界，独立子代理仅用于离线 blind 用户评价与 adversarial review，不进入产品请求路径。

### 需要验证的 Harness 模式

| 变体 | 组成 | 本轮验证方式 |
|---|---|---|
| Baseline | 无 `task_decisions` 的确定性 Planner | 同一冻结场景直接生成对照计划；不调用 LLM |
| A：Intent | 当前 Agent 将任务阶段/偏好映射到 `TaskScheduleDecision` | 实际 `create_agent()` 调用轨迹与结构化参数 |
| B：Candidate | `compare_schedule_plans` 返回经校验候选，Agent 解释取舍 | 只在场景中存在两种真实冲突目标时运行；量化新增草案、Tool 与 Token 成本 |
| C：Plan/Validate/Repair | propose Observation → 必要时 validate/重新 propose → 终止 | 覆盖创建校验失败和模糊约束；不得在 Service 内调用模型 |
| D：Critique | 同一 Agent 对合法候选按分散、连续专注、负载和 churn 软指标自检；离线子代理攻击评审 | 先记录问题证据；不先引入独立 runtime Critic |
| E：Hybrid | A + C；必要时才组合 B/D | 只有 A/C 的失败证据说明需要时才实施，避免无收益复杂度 |

## 1. 当前迭代计划

1. 复用真实场景库中的阶段化训练与备考失败用例，另请独立 Scenario Agent 构造 hold-out 用例。
2. 用同一冻结任务/日历/时间锚点比较确定性 Baseline 与真实 Time Steward Agent；关键失败用例多次运行。
3. 记录但不保存私有推理：工具轨迹、结构化参数、计划/快照、校验理由、Agent/model/tool 调用、Token 和延迟。
4. 硬约束通过服务校验；体验由盲 User Judge 与 Adversarial Critic 结构化评分，并与可计算指标交叉核对。
5. 根据最差体验修改 Prompt/Schema/确定性 Feature，再跑全部历史回归与新 hold-out。

实验数据使用专属短期用户并在结束时清理；不改真实用户数据、不自动批准计划、不执行 SchedulePlan。部署是独立步骤，本轮未请求部署。

## 2. 实验记录

### 2.1 本轮实现与架构选择

本轮沿用一个 Time Steward `create_agent()` Harness。没有把 LLM 调用移入 Planning/Task/Memory Service，也没有新增运行时 Planner Agent、Critic Agent 或 planning subgraph。实验显示语义提取、分散节奏、偏好冲突权衡、是否澄清和最小变更意图可由现有 Agent 决策；日期计算、空档、硬约束、快照、版本、事务与最终写入仍须由确定性服务控制。

Harness 闭环现在按以下方式工作：

1. Agent 经 `get_planning_context` 读取本轮任务、事件、时区与排程窗口等事实。
2. Agent 在 `propose_schedule_plan` 的 typed 参数中提交任务选择和 `TaskScheduleDecision`，明确阶段/先后、软目标时点、每日上限和有日期范围的工作时段窗口。
3. Planning Service 产生草案并返回可观测的安排与校验结果；Agent 依据返回的实际 items 与用户目标检查质量。
4. 若草案需要调整，Agent 用 `edit_schedule_plan` 编辑同一份计划；Service 对移动和锁定变更做版本、业务约束与校验。禁止为了修正草案再创建第二份重复草案。
5. 重排操作按用户明确授权调用 `reschedule_task`，由 ActionProposal/HITL 暂停等待批准；Agent 不在普通对话里再重复索要一次确认。
6. 对会改变任务顺序/取舍的关键歧义只问一个问题；在用户回答前不创建计划。

Tool catalog 仍是 44 个注册工具。用可组合的 `edit_schedule_plan` 承载草案块移动、锁定和解锁，替换更窄的 `set_schedule_plan_item_lock` 概念；此举减少工具概念而不改变总 catalog 数量。`daily_worktime_overrides` 是有起止日期的结构化窗口，和逐日事件、常规工作时间分开建模；创建、快照与后续重验均复用 deterministic service 校验。评估还增加每次请求最多一份计划的显式门槛。

### 2.2 场景、对照与运行方式

主评测集位于 `backend/apps/planning/fixtures/agent_harness_scenarios_v1.json`，包括 7 个 regression 与 3 个 hold-out：

| 场景 ID | 覆盖问题 |
|---|---|
| `release_milestones_2w` | 两周发布里程碑、截止日、会议、每日容量和缓冲 |
| `certification_study_4w` | 四周备考的阶段顺序、间隔和模拟考复盘 |
| `overcapacity_workweek` | 一周容量不足、优先级和未安排项说明 |
| `deep_work_fragmented_week` | 连续专注块与会前会后碎片任务分配 |
| `memory_explicit_preference_conflict` | 近期硬窗口与旧偏好/记忆冲突 |
| `tokyo_shanghai_travel` | 跨时区出行、日程与本地时间边界 |
| `working_parent_three_weeks` | 三周家庭与工作任务、接送/固定事项和可用窗口 |
| `minimal_churn_replan_holdout` | 事件打断后的最小移动及 HITL |
| `ambiguous_priority_clarification_holdout` | 两个同等重要任务、容量不足时先澄清 |
| `progressive_training_4w_holdout` | 四周渐进训练、恢复/减量和每周节奏 |

每个场景由同一隔离数据库快照分别运行确定性 Baseline 与真实 Time Steward Agent；真实 Agent 走 `create_agent()`、工具与 Application Service，没有直接调用内部 planner 绕过 Harness。每轮收集结构化 Agent/tool 轨迹、最终计划、校验/软指标、错误恢复、模型调用、Token 和延迟，不保存私有推理。Baseline 不调用模型。

场景是人工策划并固化的回归夹具，不是用户总体的随机抽样，也不是由被测 Planner 自己生成。7 个 regression 覆盖已知计划失败面；3 个 hold-out 增加最小变更重排、关键歧义澄清和渐进式训练。需特别说明：replan 与 ambiguity 在最终版本前用于诊断和修复，因此虽然它们最初是 hold-out 案例，经过本轮后已不能视为完全未触碰的 sealed test；它们的重复运行证明分支稳定性，不证明对新场景的泛化。

最终完整对照为每个场景各运行一次（10 场景 × 2 变体）。对关键不稳定点另做重复运行：最小变更重排 5 次、歧义澄清 5 次；此前 replan、ambiguity 的回归轮次也各重复 5 次。该设置验证了高风险决策稳定性，但并不等同于对全部 10 场景各做 5 次。

### 2.3 迭代历史与失败驱动改动

| 轮次 | 观测结果 | 根因与改动 |
|---|---|---|
| v13 | Agent 的表面通过率为 10/10 | evaluator 把“等待用户作偏好决定”与“等待审批”混成一个条件，未能真实测出澄清和 HITL 分支；因此不作为最终验收证据。 |
| v14–v15 | 分开测量澄清/审批后降至 9/10；定向 replan 两次仅一次正确走审批 | Agent 能说明最小可用时段，却会停在口头询问；少数分支可能重复生成草案。修正为“用户明确授权即调用重排工具并进入 HITL”，并强化同一草案编辑规则。 |
| v16 | replan hold-out 5/5 通过 | 明确 Harness 的审批转移，保留 Service/HITL 的写保护；重排 5 次均只选中被打断任务，未写入业务事实。 |
| v17 | 完整集 9/10；同一模糊选择被连续问两遍 | 问题在交互策略而非可行性：解释取舍时也出现变体追问。Prompt 规定只保留一个关键问句，说明文字用陈述句。 |
| v18 | ambiguity hold-out 5/5 通过 | 一问即停、不创建草案；以多次真实 Agent 运行确认澄清门槛。 |
| v19 | 最终完整对照中 Agent 10/10 | evaluator 增加“最多一份草案”指标；修正 working-parent fixture 把无关工具调用错误限定在 10/8 的问题（请求范围实际从 10/5 开始）。 |

此外将临时每日时段限制映射到按本地日期生效的硬窗口，而不是只写入 rationale；允许 Agent 在同一草案上移动项目，减少无效的重复提案。上述修正均未把日期/空档/硬约束判断交给 LLM。

### 2.4 Final benchmark 结果

最终原始记录：`backend/evaluation_reports/final-v19-10cases.json`。确定性硬约束通过 Service 校验；Agent 计划和 Baseline 计划均无硬时间违规。

| 指标 | 确定性 Baseline | Hybrid Harness Agent |
|---|---:|---:|
| 场景通过 | 8/10 | **10/10** |
| 硬时间违规 | 0 | **0** |
| 软检查通过率（逐场景宏平均） | 57.38% | **99.17%** |
| 平均模型调用 | 0 | 3.2 次/场景 |
| 平均 Agent 实际工具调用 | — | 3 次；范围 2–5 |
| 平均 Token | 不适用 | 29,673 Token/场景；总计 296,733 |
| 平均延迟 | 0.214 秒 | 9.43 秒 |
| p50 / p95 延迟 | 0.211 / 0.260 秒 | 7.43 / 34.70 秒 |
| 创建草案的场景中重复草案 | — | 0；每个计划场景最多 1 份 |

按检查点总数加权，Baseline 为 44/77（57.14%），Agent 为 67/68（98.53%）；表内与评估 JSON 的主指标采用逐场景软检查率宏平均，因此数值略有不同。Agent 的重排/澄清两例分别进入审批、问询分支，没有计划草案，故没有 schedule soft checks；Baseline 在这两例仍生成计划并计入自己的检查点分母。

质量收益主要来自跨周阶段节奏、碎片与连续深度工作分配、显式偏好优先于记忆、容量不足的解释，以及“不确定时先问/重排先审批”这些语义决策。Baseline 的两项失败分别是：无法表达用户要求的最小移动审批请求；以及在用户尚未决定优先级时仍创建部分计划。Baseline 的快和零模型成本明显优于 Agent，但不能弥补这两种交互错误与软质量差距。

唯一软检查失败是 `certification_study_4w` 的 `process_module` 落在 10 月 14 日，而 fixture 阶段期望从 10 月 15 日开始。用户请求要求四周分散并遵循备考顺序，但没有把这一日写成硬边界；其先后顺序与总体跨周安排正确。因此记录为 1 个软性阶段对齐偏差，不把它改成硬限制来追求 100%。

Agent 的一个 working-parent `get_planning_context` 调用把日期以无时区偏移的形式传入，工具校验拒绝后模型改用带偏移的日期重试；因此有 1 次恢复的工具参数错误，0 次未恢复错误。该轮多调用一次 `get_planning_context`。另有少数场景在 context 已含相关事实后又调用 `list_tasks` / `list_events`，属冗余工具调用。模型成本与 p95（主要由 memory 场景的一次 34.7 秒延迟拉高）是体验改进的真实代价；此次证据支持保留单 Agent，但不证明目前已达到低成本/低延迟的生产阈值。

### 2.5 方案对比实例

时间均按场景的 `Asia/Shanghai` 本地时区展示。

| 案例 | Baseline | Agent | 用户体验差异 |
|---|---|---|---|
| 四周备考 | 8 项集中在 10/8、10/9、10/12；两个模拟考试甚至落在相邻日期，后续练习被压缩 | 10/8 范围梳理、10/9 法规、10/14 流程、10/19 首次模考、10/21 复盘、10/23 补弱、10/26 二次模考、10/29 考前准备 | 保留阶段关系和恢复间隔，把四周计划展开；有一项比软目标窗口早一天，详见上文。 |
| 深度工作与碎片 | 报告分析与写作在 10/8 同一天，短任务也拥挤在该日 | 分析 10/8、写作 10/9；邮件/发票/回电/行动项散落至 10/8–10/14 会议间隙 | 两个深度块完整且分日，短任务填碎片时段，周末空出。 |
| 三周家庭/工作 | 六项任务压到 10/5–10/6 两天 | 六项分布于 10/6、10/13、10/16、10/20、10/22 | 使用了三周窗口，保留接送、家务与工作限制；Agent 多一次时间查询和一次恢复重试。 |
| 记忆与新窗口冲突 | 六项集中在 10/8–10/9，忽略 10/8–10/16 每天不早于 10:30 的近期约束 | 10/9、10/13、10/14、10/19、10/20、10/22，前五个受限工作日均在 10:30 后；后续沿用正常窗口 | 明确的本轮窗口优先于旧的上午偏好；这份个案的模型延迟为全组 p95 异常值。 |
| 最小变更重排 | 基线流程无法表达用户请求的最小移动并提交审批 | 只请求把被打断的 10/12 13:00–15:00 任务移到 11:00–13:00，并进入待审批；5 次运行都只移动这一项 | 不直接写库；审批前保留 HITL 安全边界。 |
| 模糊优先级 | 先安排了客户 A，客户 B 未安排 | 列出两个同等级任务与不足的可用容量，只提出一个关键选择问题，不建草案 | 把影响取舍的用户决定留给用户。 |

### 2.6 独立盲评与对抗评审

盲评输入包：`backend/evaluation_reports/blind_schedule_judge_bundle_v20.json`。它只给评审用户请求、任务/事件/时间窗和匿名随机化的 A/B 计划或行动，不含工具源代码、方法标签或候选来源映射。对有计划的两种候选，双方都省略解释文案，因此评审只比较安排与动作，不因两边都看不到的 prose 作惩罚；没有草案的澄清/审批分支则评审其实际回复和动作。

两位独立 User Judge 均完成全部 10 对比较；另有一位 Adversarial Critic 寻找最坏体验。候选 A/B 在生成包时随机排序，来源映射没有交给评审。评分结果如下（各 Judge 的 per-case 结果可在协作评审记录中复核）：

| 用户评审指标 | Judge C | Judge D（原评分 1–5，按 ×2 归一化） | 两 Judge 均值的探索性汇总 |
|---|---:|---:|---:|
| Agent 满意度均值 / 10 | 9.20 | 9.62 | **9.41** |
| Agent 中位数 / 10 | 9.0 | 9.6 | 9.3 |
| Agent P10 / 最低分 / 10 | 8 / 8 | 9.2 / 9.2 | 8.8 / 8.8 |
| Baseline 满意度均值 / 10 | 4.40 | 4.24 | 4.32 |
| Agent Would Accept | 10/10 | 10/10 | 10/10 |
| Baseline Would Accept | 2/10 | 2/10 | 2/10 |
| Pairwise：Agent 胜 / 平 / 负 | 9 / 1 / 0 | 9 / 1 / 0 | **胜 90%，平 10%，负 0%** |

Judge D 最初按 1–5 而非要求的 1–10 评分，因此以线性 ×2 归一化后展示；没有将它伪装成原始 1–10 量表。Adversarial Critic 在这份 outcome-only 数据中未发现 Agent 计划的严重体验缺陷；指出 Baseline 存在阶段压缩、没有先澄清、四周训练挤到一天、深度任务同日、出差/受影响任务之外的额外改动等问题。容量不足 case 两方案实际放入项相同，属于平局。前述判读是有限样本上的 LLM-as-a-Judge 证据，不是实际用户研究，也不能替代人工用户验收。

已知 blind-eval 边界：仅 10 个刻意构造的案例、2 位模型评审；完整 benchmark 每案例仅一次，只有重点场景做了五次稳定性复测；无真实用户偏好反馈。replan 与 ambiguity hold-out 已用于迭代，不能被当作 untouched final hold-out。A/B 方案省略文本说明，所以 overcapacity 的盲评只看相同的可行安排，而真实 Agent 回复仍解释了容量缺口和未安排项。模型供应商 Token 定价未知，因此不把 Token 换算成金额。

### 2.7 失败分类、策略沉淀与下一步

| 问题分类 | 本轮证据 | 归因 / 处理 |
|---|---|---|
| 阶段目标对齐 | 备考流程模块比软目标日期早 1 天 | 结构化软目标基本起效；剩余是偏好窗口与 Service 默认排序的边缘协调，先保留软性，不升级为硬约束。 |
| 工具参数边界 | 一次不带时区偏移的日期参数被拒，重试成功 | Agent 已能恢复但浪费调用；下一轮考虑把工具字段说明/schema 示例显式限定到含本地 offset 的 ISO datetime，并增加 evaluator 对无效参数的报表。 |
| 工具精确率 | 两处多余 `list_tasks` / `list_events` | context pack 已包含事实，Agent 仍重复查询；继续梳理动态工具暴露与何时使用专用查询工具的路由提示，不凭这点证据加新工具。 |
| 长尾延迟/成本 | memory 场景单次 34.70 秒；平均每场景 29.7k Token | 需要多次复测和生产 trace 观察后再优化上下文体积/模型调用；本轮不据一次尾值改 Memory 语义。 |
| Baseline 系统性失误 | 无用户优先级时仍产草案；不能走重排 HITL | 属于 Harness 对澄清和审批意图的缺失，不应在 Service 中通过模型补丁处理。 |

本轮从评估里沉淀出的稳定策略是：阶段型多周任务用软日期引导分散；深度任务保护连续块并尽量跨日，沟通/行政短任务可使用会议前后碎片；本轮明确时段覆盖旧的行为偏好；容量不足要显示无法安排的项目和原因；最小变更重排仅调整被打断对象并通过审批；当两个同级任务无法同时完成且用户未给取舍时，先问一个问题。稳定的时区、重叠、工作窗口、容量、版本和审批规则继续留在确定性边界，语义与权衡留在 Harness。

**是否满足“非常优秀”的停止条件：本轮实验达到继续集成候选的证据门槛，但不宣称已经达到最终产品级优秀。** Agent 硬违规为零，完整 10 案通过率 10/10，关键重排与澄清各 5/5，盲评 Agent 10/10 可接受、9 胜 1 平；最差盲评分 8/10（Judge C），另一评审归一化最低 9.2/10。限制是案例数小、全量多次稳定性不足、token/延迟显著高于确定性基线，而且存在一次软目标日期偏差。不能把“没有明显灾难计划”外推到真实用户总体。

建议的后续工作按收益/风险排序：

1. 对日期参数 schema 与提示示例收紧 offset 要求，先消除无效工具输入重试；对 `get_planning_context` 已返回的数据避免重复 `list_tasks`/`list_events`。
2. 在不增加 Planner/Critic Agent 的前提下，对 10 个场景各重复运行至少 5 次，报告 per-case 方差、P10 和最差计划；特别关注 memory 案例延迟尾部及备考软阶段窗口。
3. 另请独立 Scenario Agent 生成一组开发迭代期间不公开、未参与调优的 sealed hold-out，再做最终盲评；增加真实用户的计划可接受度反馈及一日执行变化模拟。再决定是否需要增加候选比较步骤；目前候选比较模式未进入最终主链路，单 Agent 观察—决策—修复已经满足这组场景，没有证据支撑增加运行时多 Agent 或单独 ranker。
4. 满足成本/延迟门槛后再部署并使用生产影子指标观察；本轮不含部署、真实用户写入或计划应用。

本次代码与离线评测均在本地/隔离环境完成，不修改公开 API、数据库 schema 或部署拓扑，因此没有 OpenAPI/前端类型或迁移变更。本轮独立 Docker 评测项目在复核后清理；不触碰生产服务。相关代码检查与测试结果见本轮任务最终说明。
