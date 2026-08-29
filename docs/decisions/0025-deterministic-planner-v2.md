# ADR 0025：Phase C 的确定性规划器 v2

## Context

现有 `PlanningService.propose_schedule_plan` 按任务输入顺序选择第一个空位，容量不足时抛出异常，无法表达部分可行计划，
也不能让用户知道未安排原因。Phase C 要求硬约束先验证、结果可解释，并在应用前再次校验。

## Decision

- 任务按 priority、due_at、created_at 和 id 的稳定顺序处理。
- 每个任务单独在工作时间、已有事件、已有计划任务和截止时间约束下寻找候选槽位，并与本次草案已分配槽位做冲突检查。
- 无法安排的任务保留在 `SchedulePlan.items`，状态为 `unplaced`，携带机器可读 `reason_codes`；草案额外保存 `plan_evidence`。
- 应用阶段只处理 `placed` 项，并继续锁定用户日程、检查 task version 和事务性写入。
- 当前算法仍是可解释的 deterministic first-fit v2，不声称全局最优；benchmark 继续作为对照。
- compare 只对照两种命名的确定性排序，不声称全局最优；局部重生成锁定未选中草案块，只替换选中任务并递增草案版本。
- 草案持久化约束快照、Decision Profile 快照、TTL、编辑时间和失效/放弃原因；编辑、验证、应用和放弃均使用 expected version。过期、任务版本变化、工作时间/截止期或最新冲突会使草案机器可读失效。
- 只有样本量不少于 5 且置信度不低于 0.6 的 Decision Profile 才调整任务时长，并记录 profile version/reason；低置信画像不影响排程。
- Task 的前后 buffer 进入占用区间和应用前冲突复验；持久化 planning lock 使任务返回 `task_planning_locked` 而不是被移动。可拆分任务只在 `create_linked_event_blocks` 策略下拆成满足 minimum chunk 的多个关联 Event，普通 Task 单区间策略不伪造多段时间。

## Consequences

计划可以诚实返回部分可行结果，UI/Agent 能解释 deadline 或容量失败；代价是 items JSON 需要兼容 placed/unplaced/evidence 三类记录，
当前已有生成、比较、编辑、验证、局部重生成、放弃和应用 API；后续仍需要真实数据上的加权可行性、碎片化、扰动和延迟评测。
