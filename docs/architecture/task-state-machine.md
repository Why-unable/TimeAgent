# Task 领域模型与状态机

Task 使用 UUID 主键，保存用户、可选项目名称、可选父任务、标题、描述、状态、优先级、
截止时间、预计分钟数、计划时间范围、实际开始/完成时间、来源和标签。

当前尚未建立独立 Project 模型，因此 `project` 保存可选结构化名称。父任务必须属于同一
用户，且任务层级不能形成循环。删除父任务时子任务保留并清空父引用。

时间语义严格区分：

- `due_at` 是最迟完成时间；
- `planned_start_at` / `planned_end_at` 是计划执行区间，必须成对提供且结束晚于开始；
- `actual_started_at` / `completed_at` 由状态机记录真实状态时间；
- 所有非空 datetime 必须带明确时区并统一转换为 UTC。

状态转换：

```text
pending     -> in_progress | completed | cancelled
in_progress -> pending | completed | cancelled
completed   -> terminal
cancelled   -> terminal
```

进入 `in_progress` 时首次记录 `actual_started_at`，进入 `completed` 时记录
`completed_at`。模型与数据库约束共同保证进行中/已完成状态所需时间戳的一致性。

`TaskService` 是任务写入边界：普通字段更新不允许绕过状态机或专用计划时间操作；完成任务
通过状态机记录时间且可幂等重试；重排任务会原子更新计划开始/结束时间。所有读取和写入均按
用户隔离，写操作使用事务行锁并执行完整模型校验。

REST API 的普通 PATCH 不接收状态字段，完成操作必须调用 `/api/v1/tasks/{id}/complete/`；
计划时间更新由 Service 原子执行。前端 Tasks 页面属于后续任务。
