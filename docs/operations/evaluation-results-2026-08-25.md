# Time Steward 真实模型评测记录（2026-08-25）

## 1. 目的与口径

本记录用于给项目技术底稿和后续回归提供可复核数据，不代表线上用户收益。评测在当前工作树构建的 Docker Compose 后端容器中运行，使用项目配置的 `deepseek-v4-flash`，数据库为 PostgreSQL，所有评测业务数据在用例结束后删除。报告不保存模型完整回答。

固定主评测集为 `backend/tests/fixtures/time_steward_eval.json`，覆盖 `13` 个场景、`14` 轮交互；旧时间上下文消融集为 `backend/tests/fixtures/time_steward_temporal_ablation_eval.json`，覆盖 `6` 个跨时间多轮场景。两组报告的 Token 采集覆盖率均为 `100%`。

- 工作树标识：`worktree-20260825`
- 系统 Prompt SHA-256：`8d4d40dd3392ab4ffa4b02202d70ab79230525102fee9ae17e5b961ca6ea2f7c`
- 主评测集 SHA-256：`afd5542dcccabdadca39d68453b7e558e62d3f4d3c6b471194af2d6a32efe0e1`
- 消融集 SHA-256：`2b04b0b2ca1b73700c3964844993cb2d75b8eb6d69f6f01dbf7c13c91b7e37fe`

## 2. 主评测结果

| Metric | Result |
| --- | ---: |
| Task Success | `12/13 = 92.31%` |
| Required Tool Recall | `95.83%` |
| Allowed Tool Precision | `100%` |
| 时间约束满足率 | `100%` |
| 禁用工具调用场景 | `0` |
| Tool Calls / Task | `1.69` |
| Model Calls / Task | `2.31` |
| Token / Task | `18,367.31` |
| Total Tokens | `238,775` |
| p50 Latency | `2.89s` |
| p95 Latency | `8.02s` |

唯一失败用例为 `today-schedule`：Agent 查询了当前时间和日程，但没有调用 `list_tasks`，因此 Required Tool Recall 为 `2/3`。这说明当前模型在“今日日程”聚合查询上仍可能提前结束，固定发布门禁尚未达到 `100%`。

## 3. 旧时间上下文消融

实验保持模型、Prompt、数据集和运行方式不变；实验组仅通过 `--ablation temporal-context` 移除 `TemporalContextMiddleware`。运行时当前时间锚点和 Tool 相对时间 Schema 均保留，因此本实验只验证历史消息时间消歧中间件的增量价值。

| Metric | 完整组 | 移除历史时间上下文 | 差异 |
| --- | ---: | ---: | ---: |
| Task Success | `100%` | `100%` | `0pp` |
| Required Tool Recall | `100%` | `100%` | `0pp` |
| Allowed Tool Precision | `100%` | `100%` | `0pp` |
| 时间约束满足率 | `100%` | `100%` | `0pp` |
| Tool Calls / Task | `3.17` | `3.00` | `+0.17` |
| Model Calls / Task | `5.17` | `5.00` | `+0.17` |
| Token / Task | `41,500.67` | `40,060.50` | `+3.60%` |
| p50 Latency | `7.32s` | `6.31s` | `+1.01s` |
| p95 Latency | `7.50s` | `6.80s` | `+0.70s` |

该数据没有证明 `TemporalContextMiddleware` 提升了这 `6` 个场景的任务质量；完整组反而使用了更多调用和 Token。由于每组只有一次远程模型运行，Token 和时延差异也不能直接归因于中间件。合理结论是：当前用例下，显式当前时间锚点与相对时间 Tool Schema 已足以通过测试，历史时间消歧中间件的独立收益仍需更有区分度的数据集和重复实验验证。

## 4. 后续实验

1. 将 `today-schedule` 作为回归用例重复运行，区分稳定缺陷与模型波动，并修正聚合查询策略后对比 Tool Recall。
2. 将时间消融拆成当前时间锚点、历史消息时间标注、相对时间 Tool Schema 三个独立变量，每组至少重复运行，报告均值和置信区间。
3. 扩充跨午夜、夏令时、时区切换、历史消息复用和“那天/明天”指代歧义用例，避免数据集过易导致两组同时满分。
4. 当前评测只衡量离线任务行为；个性化估时、容量建议和主动洞察仍需真实时间切分数据、用户反馈和线上 guardrail 指标验证。
