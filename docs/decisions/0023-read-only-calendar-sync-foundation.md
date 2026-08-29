# ADR 0023：Phase A 的外部日历只读同步基础

- 状态：已接受
- 日期：2026-08-23
- 取代：ADR 0008 中“不得创建连接表、同步任务”的阶段性限制
- 后续：Google OAuth、加密凭据和多日历身份边界由 ADR 0030 扩展；本 ADR 中“不注册真实 Provider”的限制已结束

## 背景

Phase A 需要把外部日历的真实 busy time 纳入后续时间上下文，但当前仓库只有 Provider Protocol 和
DTO。继续只保留协议会使同步状态、游标和来源事件无法落库，也无法验证重复同步、取消和时区语义。

## 决策

- 在 `apps.integrations` 增加 `CalendarSyncConnection`，保存用户、Provider/account/calendar identity、
  IANA 时区、启用状态、同步游标、最后同步时间和错误状态；不保存明文 OAuth Token。
- `CalendarSyncService` 接受 `ExternalCalendarProvider` 注入，调用只读 `list_events()`，将事件按
  `source + external_id` 幂等 upsert 到现有 `CalendarEvent`，保留来源、UTC 时间、状态、版本和审计；
  外部取消只取消本地镜像，不做任何写回。
- `list_events()` 返回带下一增量游标的事件页；删除可表示为只含 Provider event/calendar identity 的 tombstone。
  已存在的本地镜像收到 tombstone 后进入 cancelled 状态，未知 tombstone 不制造本地事件；Provider 游标由连接原子持久化。
- 同步允许外部事件与本地事件重叠，因为重叠本身是需要暴露给规划器的事实；不调用面向用户写入的冲突拒绝路径。
- 本阶段不注册 Google/Microsoft Provider、不实现 OAuth UI、不暴露 Token、不做 Webhook 和外部写回。
  Provider 适配器接入时必须另行设计凭据、分页、增量删除、限流和隐私策略。
- 当前提供 `IcsCalendarProvider` 作为无 OAuth 的真实只读 HTTP 适配器，并通过连接创建/同步 API 进入
  `CalendarSyncService`；同步仍不允许外部写回。HTTP 状态和传输异常先转换为不含 feed URL 的领域错误，连接状态
  只保存安全文案，避免私有订阅查询串进入 `last_error`。HTTP fetch 禁止 URL credentials、localhost 及解析到
  非公网地址的目标，并保持不跟随重定向，以收窄 SSRF 面。

## 后果

后续 Planning 可以读取带来源和新鲜度的本地事件，测试可以使用 Fake Provider 或 ICS fixture 验证同步语义；代价是当前用户
本 ADR 落地时还不能直接连接 Google/Microsoft；随后 ADR 0030 已实现 Google 只读 OAuth，Microsoft、Webhook 和
外部写回仍未实现。ICS feed 本身不提供 OAuth、分页和 webhook，且 `sync_cursor` 在没有 Provider 增量游标时只作为最近扫描水位记录。
ICS feed URL 仍作为连接标识明文保存；它可能本身携带私有访问能力，因此在把外部日历标记完成前，还需设计凭据加密、
响应隐藏和轮换策略。
ADR 0030 已通过 migration 把 `CalendarEvent` 外部唯一身份扩展为
`user + source + account_reference + calendar_id + external_id`，并对能够唯一匹配连接的旧镜像数据执行回填；无法唯一
匹配的旧数据保留显式 legacy identity，避免在迁移中猜测账户归属。
