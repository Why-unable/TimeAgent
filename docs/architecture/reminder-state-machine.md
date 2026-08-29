# Reminder 状态机

Reminder 使用 UUID 主键，并保存：

- 用户；
- 可选业务目标类型和目标 UUID；
- 标题、触发 UTC 时间和原始 IANA 时区；
- 通知渠道；
- 状态、幂等键、排队/发送时间；
- 重试次数和失败原因。

幂等键在单个用户范围内唯一。数据库为到期扫描建立
`(status, trigger_at)` 索引，并对目标引用、发送时间和失败原因设置约束。

合法转换：

```text
pending   -> queued | cancelled | missed
queued    -> sending | failed | cancelled | missed
sending   -> sent | failed
failed    -> queued | cancelled | missed
sent      -> terminal
cancelled -> terminal
missed    -> terminal
```

状态转换必须注入明确的 aware datetime；模型将其转换为 UTC。失败重试从
`failed` 重新进入 `queued` 时增加 `retry_count`。

ReminderService 使用“用户 + 幂等键”创建提醒。相同键和相同载荷的重试返回已有
Reminder；相同键但载荷不同会抛出幂等冲突，避免静默复用错误结果。创建流程先执行
完整模型校验，再依赖数据库唯一约束处理并发竞争。新建提醒及修改提醒触发时间时，调用方
必须显式注入当前时间；`trigger_at` 不晚于该时间会被拒绝。幂等重试仍可返回已经存在的
同载荷提醒，即使重试发生时原触发时间已经过去。

Celery Beat 每 30 秒触发统一扫描器。扫描器使用
`select_for_update(skip_locked=True)` 分批领取到期且仍为 `pending` 的提醒，在事务内
处理。触发时间在可配置的 `REMINDER_MAX_LATENESS_SECONDS` 宽限期内（默认 600 秒）的提醒
标记为 `queued`，提交后分别投递发送任务；更早的提醒标记为终态 `missed`，不创建任何
NotificationDelivery。发送器领取单条提醒时会再次执行同一过期判断，避免提醒入队后因
Worker 堵塞而晚到。重复任务遇到 `sending`、`sent`、`cancelled` 或 `missed` 时直接跳过。

通知渠道遵循 NotificationProvider 接口，并接收稳定的提醒发生时间与渠道投递幂等键。
当前实现 Console、Email 和 Web Push Provider。Provider 异常会记录为 `failed`；Celery
最多自动重试三次，重试从 `failed` 重新进入 `queued` 时增加 `retry_count`。

Reminder REST API 只返回当前认证用户的数据。POST 通过 ReminderService 幂等创建；
DELETE 执行状态机取消而非物理删除。前端 `/reminders` 使用生成的 OpenAPI 类型，按用户
IANA 时区展示触发时间，并提供创建、取消、状态、重试次数与失败原因展示。
