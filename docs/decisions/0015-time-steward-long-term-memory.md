# ADR 0015：Time Steward 确定性长期记忆

状态：已采纳
日期：2026-08-03

## 背景

Time Steward 需要在不同会话间参考用户稳定的时间管理习惯，例如常用地点、
日程密度、批量规划倾向和近期调整频率。聊天摘要不能替代业务事实，简报 Agent
也不应继承这类个性化上下文。

## 决策

1. PostgreSQL 中的 `CalendarEvent`、`Task`、`Reminder` 与 `ScheduleChange` 是行为统计的
   事实来源；模型输出和聊天记录不参与画像生成。
2. 每个用户只在 LangGraph `Store` 的
   `("users", user_id, "time_memory") / "profile"` 保存一份结构化画像。
   Store 是派生数据，随时可以从最近 180 天的业务事实完整重建。
3. 画像包含 7、30、180 天窗口，使用确定性 Python 统计；首版不使用 LLM、
   embedding、向量检索或地理位置追踪。
4. 事件、任务与用户直接操作的提醒 Application Service 在成功事务中写入
   `ScheduleChange` 并标记
   画像为 dirty。Celery 在事务提交后延迟重建，另有每日全量刷新兜底。
5. Time Steward 的 `before_agent` 只加载画像，`wrap_model_call` 根据当前用户
   请求筛选相关模式，并以最多 800 token 的中文只读上下文注入。运行时优先使用
   当前模型 tokenizer，失败时才回退到 LangChain 近似计数。
6. Briefing Workflow 和 Briefing Agent 不加载、不注入此画像。
7. 用户可分别关闭画像功能、画像生成和上下文注入。关闭生成时，重建任务会
   删除 Store 中的派生画像，业务事实不受影响。
8. 用户清空画像后以清空时间作为新的历史统计边界；删除单个地点或规律会写入
   PostgreSQL 排除记录，避免下一次完整重建立即恢复。
9. dirty 状态从非 dirty 首次转换时才提交后台任务；同一用户通过数据库刷新状态
   行锁串行重建，连续业务变化被合并。
10. Store 中已知的 schema v1 文档读取时确定性迁移为 v2；未知或损坏版本返回空，
    后续从 PostgreSQL 业务事实完整重建。

## 与初始设计的适配

- 当前 `CalendarEvent` 没有“已完成”状态，因此事件侧只统计非取消日程，不虚构
  完成率。
- 当前 `Task` 没有地点字段，因此常用地点只来自日程。
- 当前事件的 `source` 表示外部日历身份，不能复用为操作渠道；操作渠道单独记录
  在 `ScheduleChange.source`。
- 已有 LangGraph PostgreSQL Store 继续复用，不新增数据库或向量基础设施。

## 结果与限制

- 画像丢失不会丢失业务数据，可执行 `rebuild_time_memory` 完整重建。
- 首版规则只形成有充分 30 天和 180 天证据支持的少量稳定模式；没有证据时不
  注入任何记忆。
- 认证 API 提供当前画像与刷新状态查询、清空画像、删除地点和删除稳定规律；
  运维排查仍以 `TimeMemoryRefreshState`、`ScheduleChange` 和管理命令为准。
