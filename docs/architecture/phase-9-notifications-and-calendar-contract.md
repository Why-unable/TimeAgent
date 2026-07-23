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

本阶段仅完成接口契约，未实现任何供应商接入或同步。

`apps.integrations.calendar` 包含 Provider Protocol、可 JSON 序列化的 Pydantic DTO、能力声明和统一异常。它不依赖 Django ORM，不注册 Google/Microsoft Provider，不包含 OAuth、Token、连接表、事件映射、同步任务、Webhook 或网络调用。

## 已知投递语义

通知采用持久化队列与“至少一次”投递语义。若外部 Provider 已接收消息、但 Worker 在写回 `sent` 前崩溃，超时恢复可能再次投递；SMTP 和标准 Web Push 本身不提供统一的端到端幂等键，因此无法在本阶段彻底消除这一极小窗口。数据库去重键、行锁与终态检查可以阻止应用内部的常规重复任务，后续接入支持幂等键的 Provider 时应透传 `deduplication_key`。
