# TimeAgent Agent Harness Hardening v2

评估日期：2026-09-29  
候选基线提交：`de85034f5a74bb38ade4b01e4fcf5bdaf037a09c`  
候选源代码快照 SHA-256：`cb6bca7eca961a877985a3fcb91a721276890f4de2b830dc214c608bbb3ea5e5`（46 个源代码、测试、评测 fixture、Schema 与前端类型文件；不含临时评测设置）  
范围：本地代码、隔离评测库、合成场景和真实模型评测。未部署、未推送、未访问生产业务库。

证据标签：

- **已实现并有测试证明**：代码已修改，相关自动化检查通过。
- **实验性证据**：来自合成数据、模拟轨迹或有限次数模型运行，不等价于真实用户收益。
- **推测**：由代码与当前结果推导，尚未被充分测试。
- **未来工作**：本轮未实现。

## 1. Re-audit Findings

| 外部审查主张 | 结论 | 证据与处置 |
|---|---|---|
| ToolPolicy 只限制模型可见工具，隐藏工具仍可能被真实调用 | CONFIRMED | 原实现只覆盖模型请求的工具列表。增加真实工具执行入口的策略复核和负向测试，拒绝路径不调用工具 handler。**已实现并有测试证明**。 |
| `read_only` 下草案类工具仍可写入 SchedulePlan | CONFIRMED | `propose_schedule_plan`、`compare_schedule_plans` 会创建草案；现由执行策略拒绝只读运行中的写模式工具。**已实现并有测试证明**。 |
| 敏感或跨用户请求可因隐藏工具而绕过策略 | PARTIALLY TRUE | 原来的敏感意图判定只隐藏工具；业务服务仍按可信 actor 做用户范围过滤。新执行门阻止策略未授权调用；服务层所有权检查仍是最后边界。**已实现并有测试证明**。 |
| Memory 搜索开关关闭后，所有记忆上下文也必然关闭 | PARTIALLY TRUE | 搜索工具、写入工具、上下文注入分别由不同设置控制；关闭搜索工具不必然等于关闭上下文注入。保留其独立设置语义，没有混为一个开关。**已实现并有测试证明**。 |
| 多任务排期时隐藏 `reschedule_task` 就足够禁止逐项改期 | CONFIRMED | 可见性不能保证执行；策略现在在真实执行路径复核多任务限制。单项改期仍沿用审批边界。**已实现并有测试证明**。 |
| split 任务可能重复计入每日容量、任务指标误计 segment | CONFIRMED | 修复容量统计的单一归属口径，并分别计算任务数与计划片段数。**已实现并有测试证明**。 |
| 编辑 split SchedulePlan Item 存在身份不明确 | PARTIALLY TRUE | 单一 task 身份无法安全指向任一拆分片段；当前对不支持的拆分项编辑返回明确拒绝，避免编辑错误片段。更细粒度 segment 编辑仍未支持。 |
| 时间字段需要靠 Prompt 才能保持带时区 | CONFIRMED | 关键排程输入字段改为 timezone-aware 类型校验；服务仍按 IANA 时区转换并保存 UTC。**已实现并有测试证明**。 |

## 2. Confirmed Bugs

1. **工具授权与工具暴露原先混为一层。** Agent 只看到被过滤的工具，不代表静态 ToolNode 无法调度隐藏工具。现在 `ToolPolicyDecision` 分离 `hard_allowed_tools` 与 `visible_tools`，模型工具表过滤和同步/异步执行中间件共用决策；不可执行的调用在 handler 之前返回结构化拒绝。**已实现并有测试证明**。
2. **运行上下文缺少请求原文时，意图策略可能退化成空字符串。** 测试中的运行上下文为空，但本轮消息仍有用户请求。执行和 HITL 判定现可从最近一条 HumanMessage 补足请求文本；记忆工具路由也新增“记住”和“把专注时间改成……”用例。**已实现并有测试证明**。
3. **split 时间账本和报告口径不统一。** 修复日容量重复累加，报告中将任务数、放置任务数、片段数分开。**已实现并有测试证明**。
4. **查询容量时可把当前任务旧计划当成占用。** 任务作用域的 `get_planning_context(task_id=...)` 从数据库读取任务时长、版本和原计划，并从繁忙区间中排除目标任务，避免重排时错误压缩可用时段。**已实现并有测试证明**。
5. **空档查找先截断候选、再排序会遗漏最近可用时段。** 改为先完整生成并排序候选，再限制返回数量。**已实现并有测试证明**。

## 3. Rejected Findings and Why

- **“只要排程写工具被隐藏，真实执行就已经安全”**：NOT A BUG 不是合适结论；该主张已由最小复现确认，因此不保留旧解释，改由执行层授权保护。**已实现并有测试证明**。
- **“禁用 Memory 搜索就应同时禁用自动注入”**：NOT A BUG，前提是产品设置把搜索工具和上下文注入作为独立控制。两者作用不同；本轮保留独立开关，并要求在产品文案中说明清楚。**推测**。
- **“split 任务编辑应自动猜测目标片段”**：NOT A BUG。没有 segment 标识的编辑请求无法可靠定位目标片段，拒绝比静默选中一个片段更安全。**已实现并有测试证明**。
- **“把所有排程取舍写成固定规则可消除 LLM 错误”**：NOT A BUG。容量、冲突与时间合法性应由确定性服务校验；偏好权衡、场景语义、何时澄清仍需要模型结合上下文判断。**实验性证据**。

## 4. Harness Policy Architecture

策略现在明确区分三件事：运行级执行权限、模型可见工具表、HITL 是否需要中断。

- `resolve_tool_policy()` 汇总 actor、只读状态、用户请求工具包、多任务改期限制和 Memory feature flags。
- `ToolPolicyMiddleware.wrap_tool_call()` 与 `awrap_tool_call()` 在执行前复核 hard allowlist；可见性不再充当授权边界。
- 隐藏但仍被模型请求的授权工具返回 `tool_surface_mismatch`，可恢复到可见工具表；真正未授权调用返回不可重试拒绝；未知工具不会调用业务 handler。
- `HumanInTheLoopMiddleware` 只对当前请求有权且可见的高风险写工具应用审批策略。批准仍由 ActionProposal 审批和恢复流程驱动，本轮没有自动批准任何操作。
- Compact planning surface 将 22 个工具缩至代表性请求下的 12 个，同时保留核心规划、复核、审批和应用路径；不影响执行授权。

**已实现并有测试证明**：全后端测试中包含隐藏写工具、只读草案、HITL 和记忆写入审批回归。

## 5. Planner Correctness Fixes

- split task 的每日容量由唯一任务事实计账，计划片段不再重复扩增任务估时。
- 新计划选中已有 planned task 时，不把其旧计划区间算作外部 busy time。
- Planner 先生成完整空档候选，再排序截取；新增回归覆盖最近空档被旧截断逻辑丢弃的问题。
- `get_planning_context(task_id=...)` 将数据库事实与模型提议分开：时长、版本、原计划、截止时间来自可信任务记录；模型无法用不匹配的估时或旧计划参数覆盖它们。
- 草案仍需经过验证、编辑或放弃；高风险应用仍由 HITL 控制。

**已实现并有测试证明**：服务层容量、空档、重排、计划编辑、时区和策略测试；全后端测试结果列于第 9 节。

## 6. Capacity Semantics

统一定义：`total_capacity_minutes` 是偏好工作时段可提供的总量；`committed_minutes` 是已有事件及受保护计划实际占用；`remaining_minutes = max(0, total_capacity_minutes - committed_minutes)`。可安排容量使用剩余量，同时保留未安排/已承诺的独立字段，不将原始总量与净剩余量混用。API 响应、Agent 工具和前端容量页面已对齐此口径，并更新 OpenAPI 与生成类型。

**已实现并有测试证明**：容量与 split 场景测试、Django system check、迁移检查通过。

## 7. Split Task Semantics

任务是业务事实单位，segment 是排程单位。任务总时长只计一次；每个 segment 记录时段和片段时长；指标同时提供放置任务数、未放置任务数、片段数和放置分钟。当前编辑工具以 task/plan 身份为主，不支持选择特定拆分片段；遇到无法无歧义编辑的拆分项会显式拒绝。

**已实现并有测试证明**：容量与计划指标回归通过。  
**未来工作**：若要编辑单独片段，应先引入稳定的 segment 身份和相应并发版本校验，再设计面向用户的 segment 操作。

## 8. Time Schema Improvements

排程相关 API 使用 aware datetime 验证，拒绝无时区时间值；内部数据库仍统一保存 UTC，用户输入、日历占用与显示通过明确 IANA 时区转换。Prompt 负责解释用户时间，不承担格式正确性的最后保证。

**已实现并有测试证明**：schema、计划服务和跨时区场景测试；`manage.py check`、迁移检查通过。

## 9. Regression Results

最终提示词候选使用正确加载的本地 DeepSeek 配置，在 10 个公开合成场景上运行 3 次，Agent 30/30 通过、逐案例 3/3；硬违规、灾难性失败和工具错误均为 0。确定性 baseline 只适用于其中 8 个场景，单次通过 4/8。两者样本数与调用预算不同，不宜将耗时或通过率作等量比较。

| Variant | 样本 | 通过 | 硬违规 | 平均延迟 | P50 / 最大值 | 平均 Token | 模型 / 工具调用 | 软检查均值 | 灾难性失败 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Deterministic baseline | 8 | 4 | 4 | 0.235s | 0.240s / — | — | 0 / 0 | 51.19% | 4/8 |
| Time Steward Agent | 30 | 30 | 0 | 6.560s | 6.540s / 10.641s | 38,532 | 3.17 / 3.27 | 95.00% | 0/30 |

软检查分数来自 24 次有排程的运行：中位数 100%，最差单次 50%。低分集中在用户只要求长日期范围、但没有明示每日上限或最少分散天数的“记忆偏好冲突”场景；模型有时把任务压在最早两天。该项是软质量波动，不是硬约束或通过率失败。两种尝试用更强的跨周分期指引改善它，都使日期窗口诊断集降到 4/6 通过，已撤回；最终候选保留原有的跨工作日缓冲规则。

另在公开 V3 诊断集运行 30 个回归案例各一次：30/30 通过、无硬违规，1 次 `edit_schedule_plan` 错误被恢复、未解决工具错误为 0。临时日期窗口专项测试在最终提示词上 6/6 通过、软检查全通过；其中 1 次可恢复编辑错误。澄清专项测试 5/5 通过，均只问一个问题并点名待选任务，且未创建草案。上述是单独诊断结果，不并入 10×3 主表。

主评测脱敏数据：`artifacts/deepseek-public-final-10x3-20260929-sanitized-runs.json`、`artifacts/deepseek-public-final-10x3-20260929-summary.json`。V3 诊断：`artifacts/deepseek-post-window-fix-20260929-v3-sanitized-runs.json`、`artifacts/deepseek-post-window-fix-20260929-v3-summary.json`。日期窗口专项：`artifacts/deepseek-final-date-window-retest-20260929-sanitized-runs.json`；澄清专项：`artifacts/deepseek-clarification-one-question-20260929-sanitized-runs.json`。原始评测只保存在被忽略的本地评测目录。固定合成数据不能直接推断真实用户收益。

## 10. Sealed Hold-out Methodology

本轮没有生成或运行新的 sealed holdout。为避免误读、复用或由旧结果泄漏期望，没有打开工作区已有旧 sealed 产物，也没有引用其中的场景或指标。本报告不宣称通过 sealed 验收。

先前记录的公开 V3 评测 27/30 次模型 API 异常，在显式加载项目本地 `.env` 并使用 DeepSeek 配置后未能复现；本轮 30 次调用全部完成，只有 1 次可恢复的排程编辑错误。旧错误的确切根因仍未证明，不能归因于模型名、代理或凭证中的某一项。运行日志显示实际使用 `deepseek-v4-flash` 配置；官方更新说明截至 2026-09-10 将其列为临时兼容名称并路由到 V4.1-Flash。[DeepSeek API 更新记录](https://api-docs.deepseek.com/updates/)

下一次 holdout 应在模型服务连通性被验证后，由独立流程新生成并封存；候选代码和场景固定后才执行一次正式评估。旧 sealed 资料不得作为新基准。

## 11. Multi-run Stability

公开 Agent 集为 10 场景 × 3 次。每个场景均 3/3 通过；硬违规、灾难性失败、未解决工具错误均为 0。软检查均值 95.00%，24 个有计划结果的中位数为 100%、最差 50%。DeepSeek V3 诊断 30/30 通过，其中 1 次编辑错误被恢复。6 次日期窗口专项运行全部通过；5 次澄清专项也全部通过。重复次数能发现明显不稳定行为，但不足以估计生产长尾或低频风险。

Baseline 只有 8 个适用场景各 1 次，其中 4 次失败。没有本轮新 sealed 多轮结果。

## 12. Blind Pairwise Evaluation

两位独立评审只看到同一组 8 个公开合成案例、用户请求、任务/事件事实与匿名 A/B 排程；A/B 映射在两份输入中互换。没有向评审提供期望值、工具轨迹或候选身份。评审完成后，才将排程时间与冻结候选评测轨迹对齐以还原身份。

| 评审 | 候选胜 / 平 / 负 | 候选可接受 | 候选平均分 /10 | baseline 平均分 /10 |
|---|---:|---:|---:|---:|
| C | 7 / 1 / 0 | 8/8 | 8.50 | 3.25 |
| D | 7 / 1 / 0 | 8/8 | 9.00 | 3.88 |
| 合计 | 14 / 2 / 0 | 16/16 次判断 | 8.75 | 3.56 |

两次平局都来自“容量不足时先排紧急/高优先级任务”案例；评审指出最终答复还应解释低优先级任务为何未安排。盲评支持候选在这些合成案例中更贴合任务顺序、截止时间、每日容量和生活节奏，但评审模型评分不是用户研究，也不替代新的 sealed 测试。输入文件为 `artifacts/harness-v2-public-final-blind-judge-c.json` 与 `artifacts/harness-v2-public-final-blind-judge-d.json`。

## 13. Tail-risk Analysis

主公开集 30 次中，硬约束失败 0、灾难性失败 0、计划校验失败 0、工具错误 0。V3 诊断集 30 次中有 1 次可恢复的 `edit_schedule_plan` 错误，无未解决错误。之前报告的 provider 异常在当前正确加载 DeepSeek 配置后没有再出现，但旧异常根因未知。

盲评 16 次判断中候选 14 胜、2 平、0 负，且均被判为可接受。该结果只覆盖 8 个合成案例，不涵盖真实日历噪声、历史记忆偏差、极端时区边界或生产服务降级；因此只能说明本次观察到的尾部风险，不足以断言不存在长尾问题。

## 14. Token / Latency Analysis

此前标准工具面公开 Agent 均值为 38,532 Token/次、3.17 次模型调用、3.27 次工具调用；平均延迟 6.560 秒，中位数 6.540 秒，最慢 10.641 秒。该评测摘要没有计算 P95，因此报告最大值而非估算 P95。Token 是单轮内多次模型调用的累计记录，不是单一上下文窗口长度。

此前标准工具面 30 次运行累计输入 breakdown：system prompt 800,209 tokens、tool schema 399,320、tool observation 231,090、conversation 16,358、memory context 828。系统提示与工具 schema 仍占主要输入。后续可以压缩重复说明，但必须在同一公开回归、工具轨迹和盲评标准下对比，不能仅为降 Token 隐藏未验证的工具。

### Tool Architecture follow-up（2026-09-29）

按 `docs/optim/toolset-optim.md` 完成 44 个注册工具的审计。注册能力不减少；Agent 默认使用 compact planning surface，并在草案生成后隐藏重复的 `propose_schedule_plan` / `compare_schedule_plans`，但保留 `get_planning_context` 供修复时重读。`get_current_datetime` 改为只在明确钟表时间请求中暴露，因为固定本地时间锚点已在 Runtime system message 提供。`change_task_state` 的 Agent Schema 收窄为 `in_progress`，避免绕过单任务取消的 HITL；完成与取消分别保留为有不同语义的工具。

同一 DeepSeek 模型、同一 10 场景 × 3 次公开回归的组合候选结果：30/30 通过，硬违规 0，工具错误 0；平均可见工具 7.3（标准面 10.5），平均工具调用 2.03（标准面 3.27），平均总 token 33,073（标准面 38,532），累计工具 Schema token 318,159（标准面 399,320）。平均延迟 6.429 秒、P50 7.012 秒，不能据小样本声称延迟普遍下降。软质量均值从 0.950 到 0.992，但新候选把 intent route、阶段过滤、钟表工具路由、系统提示和任务状态 Schema 一起变更，因此结果只能归因于组合候选，不能归因于单项改动。详情和 44-tool audit 在 `docs/experiments/tool-architecture-optimization-20260929.md`，脱敏汇总为 `artifacts/deepseek-tool-architecture-comparison-20260929-summary.json`。

## 15. Whole-day Simulation

DeepSeek 配置恢复后，以最终提示词在 2026-10-05（Asia/Shanghai）重跑 6 个合成检查点，覆盖初始计划、任务提前完成、估时超时、新增会议、任务取消和紧急任务加入。计数器修复后共记录 20 次工具调用、4 个草案、12 次任务移动、累计 840 分钟位移；HITL 中断 0，批准 0。每步当前计划快照的“逾期任务数 / 未排活动任务数”为：08:00 0/0，10:00 0/0，11:30 1/1，13:00 3/3，15:00 3/3，16:00 4/4。全过程没有会议冲突、工作时间违规或时长不一致，但超时与会议导致容量不足，草案留下未安排任务；需要继续验证 Agent 是否清楚解释未安排原因和取舍。10:00 与 15:00 步骤被评为 `ask`，可能有不必要的追问，需后续盲审最终答复。脱敏结果：`artifacts/deepseek-day-trajectory-toolcount-fix-20260929-sanitized.json`。

这轮还修复了评测器按历史消息长度切片工具轨迹的问题：摘要中间件缩短历史时可能漏记本轮调用。现在扫描返回消息并按工具调用 ID 去重；相关定向测试 8/8 通过。轨迹结果只覆盖一个模拟工作日，不能代表多日生产稳定性。

## 16. Memory Longitudinal Evaluation

- `test_longitudinal_memory_calibration_changes_next_day_duration_decision` 使用 5 个历史完成样本构建 30 日校准；记忆启用用户得到 90 分钟建议，禁用用户保留 60 分钟输入估时。禁用记忆时不会重建行为档案。**已实现并有测试证明**。
- 语义记忆 Policy Golden Set 12/12 通过；启用策略准确率、shadow policy 准确率、显式意图、敏感内容拒绝和 Prompt Injection 拒绝均为 100%。Artifact：`artifacts/semantic-memory-policy-golden-v1.json`。
- 以上为受控合成基准，不证明对真实用户偏好的识别准确率，也不证明跨月长期收益。Memory 必须持续遵守 PostgreSQL 业务事实权威与 Memory Policy 写入边界。**实验性证据**。

## 17. Remaining Technical Debt

1. 旧 V3 评测中 27/30 provider 错误尚无确切根因；正确加载 DeepSeek 配置后未能复现。评测环境的长期语义记忆 fixture 还会出现本地 Celery 投影入队 `ImproperlyConfigured` 告警，记忆 projection 的端到端路径未在本轮验证。**未来工作**。
2. 当前没有针对冻结候选的新 sealed holdout 结果；需要在 provider 恢复后创建全新数据集进行独立验收。**未来工作**。
3. 最新全日轨迹暴露容量下降后有 1–4 个未安排任务，需检查最终答复是否明确列出未安排项、截止风险及其原因；取消任务后的稳定性说明也需盲审。**未来工作**。
4. 单独 split segment 编辑尚无稳定业务身份；若支持，应先引入 segment 身份和并发版本校验。**未来工作**。
5. 工具 Schema 与 system prompt 仍是主要输入成本。首轮按意图/阶段缩窄工具面已验证有效；`get_planning_context` 仍有 12 个参数和较长说明，是否拆为 context/free-slot 两个原子读取工具需单独 A/B，不能仅凭 Schema 大小决定。**实验性证据 / 未来工作**。
6. 10 个公开案例各重复 3 次仍不足以覆盖生产长尾；长期个性化也依赖可信且经用户允许的完成记录。**未来工作**。

## 18. Final Recommendation

当前公开基准的硬约束证据较强：最终候选 30/30 通过，无硬违规、灾难性失败或工具错误；日期窗口和澄清专项分别 6/6、5/5。V3 诊断集也 30/30 通过，但发生 1 次已恢复的编辑错误。此前盲评结果在 8 个案例上累计为 14 胜、2 平、0 负，候选 16/16 次判断可接受；它们仍是合成用例评估。

目前不应称为生产级“优秀”：没有新的独立 sealed holdout；全日模拟在容量收紧时有 1–4 项任务未安排，取消任务后还需要更清晰地解释计划状态；本地 Memory projection 入队告警未解决。工具面组合候选通过了公开回归，但仍须观察更广的非排程意图和生产流量。下一步应先改进这些可观察的用户结果，再由独立流程封存全新 holdout 并复测全日轨迹。任何新的硬约束失败应先转为公开回归，再用另一套新 holdout复核。

全后端测试 624 passed、3 skipped；Django system check 与 `makemigrations --check --dry-run` 通过，Ruff lint 与全部修改路径格式检查通过。全仓 `ruff format --check .` 仍报告 43 个既有文件需要格式化，本轮没有触碰这些范围外文件。前端 111 个测试、lint 与生产构建通过；构建仍提示已有 chunk 偏大。代码目前只在本地工作区，未提交、未推送、未部署；评测未连接生产业务数据库，也未自动批准 HITL。
