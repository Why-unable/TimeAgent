# ADR 0008：独立通知投递与外部日历契约边界

- 状态：Accepted
- 日期：2026-07-21

## 背景

Phase 2 的 Reminder Dispatcher 直接选择 Console Provider，并把渠道发送结果写回 Reminder。Phase 7/8 的 BriefingRun 则只持久化简报，没有统一渠道投递记录。这使业务事件、异步重试和供应商协议混在同一职责中，也无法表达同一提醒通过多个渠道独立成功或失败。

Phase 9 同时需要为未来外部日历接入建立稳定边界，但当前不具备 OAuth、Token 生命周期和同步冲突策略的产品需求，不应创建伪连接模型或不可用页面。

## 决策

1. 新增独立的 `NotificationDelivery`。Reminder 与 Briefing 只描述业务事实；Delivery 描述某一来源通过某一渠道的一次持久化投递。
2. 状态变更只能经过 `NotificationService`。Celery 负责排队、超时、指数退避、抖动和恢复；Provider 只翻译外部协议，不直接修改 Delivery、Reminder、Briefing 或 Subscription。
3. Provider 通过 Protocol 和 Registry 选择，不在业务代码散落渠道判断。原 Console Provider 迁入统一接口；Email 使用 Django Email Backend；Web Push 使用 VAPID/Web Push 协议。
4. 第一版只允许通知当前用户本人。Email 地址来自 `user.email`，Web Push Subscription 必须属于当前用户。第三方收件人未来必须走 ActionProposal/HITL。
5. Reminder 的 `sent` 表示到期 occurrence 已可靠移交给通知子系统，不代表每个渠道都成功。每个渠道的最终结果由 Delivery 独立记录。
6. BriefingRun 只有在 `completed` 或 `partial` 且结果已持久化后才能创建 Delivery；失败 Run 不发送成功内容。
7. 外部日历在 Phase 9 只提供不依赖 Django ORM 的 Provider Protocol、Pydantic DTO、能力声明；Phase A
   的只读连接/同步基础由 ADR 0023 取代。Google/Microsoft Provider、OAuth、Token、Webhook 和外部写回
   仍不在当前范围。

## 理由

- 通知独立于 Reminder 后，一个业务事件可以产生多个渠道记录，渠道失败不会篡改原始业务事实。
- Provider 不修改模型，可在普通测试中使用 Fake/locmem 实现，并让重试、审计和用户隔离保持在 Application Service。
- 只通知用户本人可避免任意第三方外发这一高风险动作，同时满足提醒和简报的个人投递闭环。
- 外部日历先固定契约，可提前统一 UTC/IANA 时区、DTO 和异常语义，而不会以空模型和伪 API 制造错误完成感。

## 后果

- 通知的状态查询以 `NotificationDelivery` 为准；Reminder 状态不再承载渠道失败细节。
- SMTP 和 VAPID 配置只注入 Django/Celery。前端仅通过认证 API 读取 VAPID 公钥。
- 真实 SMTP/Web Push 验证必须显式启用；默认测试不访问外部服务。
- Phase 10 如需真实外部日历接入，必须另行记录 OAuth、Token 加密、同步映射和冲突策略 ADR。
