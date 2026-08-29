# ADR 0027：未来空闲时间推荐 API

## Context

用户需要的不只是“有没有空”，还需要基于真实事件、已计划任务、工作时间和时区的可行动候选。前端或 LLM 自己计算会产生
冲突、DST 和权限边界错误，也无法保证与 planner 使用相同规则。

## Decision

- 新增只读 `GET /api/v1/planning/free-time-recommendations/`，所有时间参数必须带时区。
- 由 `FreeTimeRecommendationService` 调用现有 `PlanningService.find_free_slots`，复用工作时间、事件、计划任务、半开区间和 IANA 时区规则。
- 每个候选返回 `reason_codes`；无候选时返回明确的 `fallback=no_valid_slot`，不凭空制造时间。
- 当前不自动创建任务或日历事件；需要写入时继续走 Plan Preview/HITL。

## Consequences

该 API 可被 Today、Tasks、Android 和 Agent 复用，规则只有一个后端来源；代价是推荐仍是 first-fit 候选，不代表全局最优，需后续 benchmark 验证排序质量。
