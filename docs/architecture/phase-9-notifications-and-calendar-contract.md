# Phase 9：通知投递与外部日历契约

## 通知调用链

```text
Reminder due / BriefingRun completed
  → Application integration service
  → NotificationService.create_delivery()
  → PostgreSQL NotificationDelivery
  → Celery notifications.send
  → NotificationProviderRegistry
  → Console / Django Email / Web Push
  → NotificationService.mark_sent() / mark_failed()
```

`deduplication_key` 由业务来源、occurrence/run 和渠道组成。重复 Celery task 在获取到 `sent`、`cancelled` 或已经发送中的记录时安全退出。Worker 在 `sending` 中崩溃后，周期扫描会把超时记录恢复为 `queued`。临时错误按上限进行指数退避和随机抖动；永久错误保留失败记录且不无限重试。

Reminder 的 `sent` 表示到期 occurrence 已交给持久化投递系统。Console、Email、Web Push 各自拥有 Delivery，任何一个渠道失败都不会覆盖其他渠道结果。Briefing 仅在结果持久化为 `completed`/`partial` 后创建 Delivery。

## Provider 边界

Provider 接收纯 DTO `NotificationMessage`，返回 `ProviderSendResult`，不查询 Reminder/Briefing，不修改 ORM，不决定重试。Registry 是渠道到实现的唯一映射点。日志只包含 Delivery/User/来源/渠道/尝试次数/延迟/错误码，不记录正文、邮箱凭据、VAPID 私钥或完整 Push endpoint/key。

Email 只发送给 Django 当前用户的 `email`。Web Push Provider 接收 Service 构造的当前用户有效 Subscription DTO；HTTP 404/410 会返回失效 ID，再由 Service 禁用对应记录。

## 前端与安全

`/settings/notifications` 显示 Email 开关、Web Push 权限和订阅状态及最近投递。页面不会在首次加载时请求通知权限；只有“启用浏览器通知”按钮触发 `Notification.requestPermission()`。Service Worker 处理 Push 展示和点击跳转。VAPID 私钥不进入 `VITE_*` 或前端构建产物，前端只从认证 API 获取公钥。

生产 Web Push 需要 HTTPS；localhost 可用于开发测试。真实 SMTP/Web Push 测试默认跳过，必须显式设置 `RUN_LIVE_NOTIFICATION_TESTS=1` 并使用专用用户本人凭据。

## 外部日历状态

Phase 9 的 Provider Protocol 仍是外部供应商的边界；Phase A 在其上增加了只读同步基础。

`apps.integrations.calendar` 保持 Provider Protocol、可 JSON 序列化的 Pydantic DTO、能力声明和统一异常；
`apps.integrations` 增加 `CalendarSyncConnection`、只读同步 Service 和连接状态 API。Phase A 后续注册了
`GoogleCalendarProvider`：服务端 OAuth state 只存 SHA-256 摘要，Token 以独立 Fernet key 加密并可轮换；
CalendarList/Events 分页有上限，sync token 410 只触发一次指定时间窗全量对账，删除以 tombstone 进入本地取消状态。
外部事件身份包含 provider/account/calendar/event 四个维度，公共 Event API 不能伪造这些字段。

前端只接收 authorization URL、连接 UUID、展示名和同步状态，不接收 account/calendar 原始标识或 Token。Nginx 对
OAuth callback 精确路径关闭 access log，Django 请求日志只记录不含 query string 的 `request.path`。集成保持只读；
`verify_google_calendar` 复用同一 Provider 与 `CalendarSyncService` 生成版本化脱敏沙箱报告，报告只记录计数、状态、
耗时和是否重置游标，不输出外部身份、URL、游标或凭据。它是验收入口，不是后台同步任务。
Microsoft、Webhook 和外部写回不在当前边界；当前仅实现有界 Celery 后台轮询。具体见
[ADR 0023](../decisions/0023-read-only-calendar-sync-foundation.md) 与
[ADR 0030](../decisions/0030-google-calendar-oauth-read-only.md)。

## 已知投递语义

通知采用持久化队列与“至少一次”投递语义。若外部 Provider 已接收消息、但 Worker 在写回 `sent` 前崩溃，超时恢复可能再次投递；SMTP 和标准 Web Push 本身不提供统一的端到端幂等键，因此无法在本阶段彻底消除这一极小窗口。数据库去重键、行锁与终态检查可以阻止应用内部的常规重复任务，后续接入支持幂等键的 Provider 时应透传 `deduplication_key`。
