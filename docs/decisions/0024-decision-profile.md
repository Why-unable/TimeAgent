# ADR 0024：Phase B 的版本化时间决策画像

## Context

Phase A 已经产生了任务执行信号和估时校准，但规划、前端和未来 Agent 不能直接读取自由文本 Memory 或自行拼接统计。
Phase B 需要一个可解释、可禁用、可追溯的个人时间决策边界，同时保持 PostgreSQL 事实与可重建 Memory 的分离。

## Decision

- 新增 `DecisionProfileService`，组合 `UserPreference`、Time Memory 的 30 天执行校准和用户反馈。
- 当前只实现 `duration_estimate` 类别：冷启动固定 30 分钟；全局画像使用限制在 0.25 至 4.0 的实际/预计时长倍率；任务级建议优先使用至少 3 个样本的明确 project/首 tag 分组，其次使用版本化中英文确定性 taxonomy 的语义类别，再回退全局画像。分类器会诚实返回 `unclassified` / `ambiguous`，不调用 LLM，也不把标题自由文本写进长期画像。
- 派生执行证据使用 60 天半衰期的时间衰减；任务建议携带 classifier/feature version、7 天 `expires_at` 和校准后的置信度。特征级 disable 只禁用匹配 segment，无 segment 的 disable 才是全局控制。
- 输出版本、来源、样本量、置信度和 evidence；消费方不得读取原始模型推理或直接依赖 Memory JSON。
- 用户的 accept/override/disable/too-short/too-long 反馈写入 PostgreSQL `TimeDecisionFeedback`，使用用户级幂等 key。override/disable 是全局控制信号；任务级准确度反馈不得遮蔽它们。too-short/too-long 只在相同明确 project/首 tag 分组中调整下一次建议。
- Web 与 Capacitor Android 共用任务级建议 UI 和反馈 API；客户端只标记来源，不复制分组、倍率或回退规则。
- 画像是派生决策输入，不改变任务、日历或提醒事实；高风险动作仍遵循现有 HITL。

## Alternatives

- 直接把统计塞入 `UserPreference.planning_rules`：实现快，但无法审计反馈历史，也会混淆声明偏好与派生结果。
- 让 Agent 读取完整 Memory 并自行解释：上下文不可控、难评测，且可能把低置信模式当成硬规则。
- 现在引入独立模型服务：超出当前数据规模和 Phase B 验收范围，增加部署与一致性成本。

## Consequences

正面：规划和 UI 获得稳定 typed boundary，用户反馈可撤销/审计，低样本明确回退；代价是新增迁移、反馈 API 和版本管理。
当前限制：语义分类是小型、版本化、可测试的规则 taxonomy，不是 embedding/训练模型，因此覆盖率受词表限制；校准误差输出仍只是对当前置信度启发式的离线检验。仓库没有真实留出集性能数据，这些指标必须在真实执行样本上补测。
