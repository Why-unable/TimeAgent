# Redis Streams 事件桥接重构记录

> 更新时间：2026-08-29
> 状态：Phase 1 主链路与 correctness hardening 已实现；隔离 Redis E2E 部分通过，主 Compose Redis 验收被 AOF 损坏阻塞；Phase 2 暂缓

## 1. 背景

Time Agent 原有 SSE 通过 PostgreSQL `AgentEvent` 表按 `sequence` 每 250ms 轮询。PostgreSQL 仍然适合作为可靠、可回放的事件事实源，但在线 SSE 连接在没有新事件时也会持续查询数据库，因此需要增加实时事件通道。

本次重构采用：

```text
AgentRun
  -> PostgreSQL AgentEvent（权威、持久化）
  -> Redis Streams（实时加速、可丢失）
  -> SSE
```

Redis 不替代 PostgreSQL，也不改变前端的 SSE 协议。

## 2. 已完成

### 2.1 事件发布

- 新增 `backend/apps/conversations/event_stream.py`。
- 新增 `RedisAgentEventStream`，按 Run 使用独立 Stream key：
  `timeagent:agent-events:{run_id}`。
- `AgentRunService.append_event()` 仍在事务内创建 PostgreSQL `AgentEvent`，由数据库生成权威 `sequence`。
- 通过 `transaction.on_commit()` 在数据库提交后 best-effort 发布 Redis，避免数据库回滚后 Redis 出现“幽灵事件”；当前发布回调同步执行，不宣称为后台异步队列。
- Redis 发布失败只记录 warning 并返回失败，不影响 AgentRun 和 PostgreSQL 提交。
- Redis Stream 保存完整 SSE 所需字段：`sequence`、`event_type`、`payload`、`created_at`。
- 每个 Stream 最多保留约 1000 条事件，TTL 为 24 小时；完整历史仍由 PostgreSQL 保存。

### 2.2 SSE 读取

- 连接建立时先验证用户对 Run 的所有权。
- 再从 Redis 记录当前 Stream 基线位置；空 Stream 使用稳定起点 `0-0`。
- 再按客户端 cursor 从 PostgreSQL 补发历史事件。
- 补发完成后使用 Redis `XREAD BLOCK` 获取实时事件。
- Redis 返回的事件仍按 PostgreSQL `sequence` 去重，避免 catch-up 与 live 切换时重复发送。
- 如果 Redis 事件出现 `sequence` gap 或乱序，先从 PostgreSQL 按 sequence 对账，不直接跳过中间事件。
- Redis 不可用、连接超时或读取失败时，当前 SSE 连接自动退回 PostgreSQL polling。
- 客户端断线重连仍使用原有 `cursor` / `Last-Event-ID`，无需修改前端。
- 没有使用 Consumer Group，多个设备可以独立读取同一个 Run 的全部事件。

### 2.3 配置与测试

- 新增 `AGENT_EVENT_STREAM_ENABLED`，可在测试或无 Redis Stream 环境关闭。
- 新增 `AGENT_EVENT_STREAM_REDIS_URL`，默认使用 Redis logical DB 2，与 Celery 默认 DB 逻辑隔离。
- 增加 Redis 发布成功、发布失败、事务提交后回调、空 Stream 基线和 sequence gap 对账测试。
- Redis 连接、读取和发布均设置有限超时，避免 Redis 故障阻塞 SSE 建连或 Agent 事务。
- Redis 客户端按 URL 复用进程级连接池，SSE 读取不再为每次 `XREAD` 创建和销毁连接。
- Async Redis 连接池按 event loop 隔离，避免测试或多 loop 场景出现 `Future attached to a different loop`。

## 3. 当前未完成

以下内容没有在本轮实现：

1. Transactional Outbox：当前依赖 `on_commit` 回调；进程在数据库提交后、Redis 发布前被终止时，Redis 可能缺少该事件。SSE 会在 heartbeat/polling fallback 中从 PostgreSQL 找回，但没有独立 outbox 重放器。
2. Durable/Transient 事件拆分：当前 `message.delta` 仍沿用现有 AgentEvent 持久化链路，没有改成 Redis-only 高频流。
3. Redis Stream 与 PostgreSQL 的专用 reconciliation worker：当前依靠 SSE fallback，不主动回填 Redis。
4. 多连接高并发压测、Redis 阻塞唤醒延迟、数据库查询下降比例、SSE p95/p99 和 fallback 比例。
5. 主 Docker Compose Redis 下的完整端到端验收：现有 Redis AOF 增量文件损坏，容器无法健康启动；未删除或重建其持久卷。
6. 生产服务重建和真实移动端回归。

## 4. 验证结果

- Ruff：通过。
- Django system check：通过。
- `makemigrations --check --dry-run`：无新增迁移；本机 PostgreSQL 未启动时会产生连接警告。
- 事件流、聊天和 Agent 专项测试：`35 passed, 1 skipped`；事件流专项在 correctness hardening 后为 `5 passed`。
- Redis fallback 专项单元测试：Redis `read` 抛异常后，SSE 能切换到 PostgreSQL polling；事件流专项当前为 `6 passed`。
- 后端全量测试：`478 passed, 3 skipped, 1 failed`。
- 唯一失败为既有 `test_false_positive_cancels_pending_delivery_and_disabled_kind_is_not_materialized`，固定测试日期已早于当前系统时间，与本次 Redis/SSE 代码无调用关系。

### 4.1 隔离 Redis E2E 结果

使用同一 Compose 网络上的临时无持久 Redis 完成了组件级真实验收：

| 场景 | 结果 | 证据 |
|---|---|---|
| 正常 AgentEvent → Redis Stream → 读取 | 通过 | 发布后 `XLEN=1`，实际读取 sequence=1 |
| DB catch-up → Redis live | 通过 | baseline 后新增事件实际读取 `[2]` |
| Redis 中断期间 PostgreSQL 提交 | 通过 | Redis 停止时 AgentEvent sequence=1 成功写入，发布 warning 后继续 |
| Redis 恢复后新连接读取 | 通过 | 临时 Redis 重启后新 Stream event 可被 `XRANGE` 读取 |
| 连续 `message.delta` | 通过 | 实际读取 sequence `[1..10]`，无缺失、无重复 |

上述不是主 Redis 持久卷的生产验收。主 Redis 当前日志显示 AOF 增量文件格式损坏，需由运维决定备份/修复/重建策略后，才能完成原 Compose 环境的 kill/recovery 验收。

## 5. 关键边界

- PostgreSQL `AgentEvent` 仍是审计、重连、回放和故障恢复的唯一权威来源。
- Redis 只负责降低实时等待和空轮询成本，不能作为业务状态、记忆或事件历史的替代存储。
- Redis 发布不能放在数据库写入之前，也不能让 Redis 故障导致 AgentRun 失败。
- SSE 的客户端 cursor 仍然是 PostgreSQL `sequence`，不是 Redis Stream ID。
- 事件流读取不使用 Consumer Group，避免多个客户端之间发生竞争消费。

## 6. 后续 Phase 2 建议

只有在压测证明当前方案的 PostgreSQL 写入或 SSE 事件量成为瓶颈后，再考虑：

```text
Durable:
  agent.started / tool.completed / approval.required / message.completed
  -> PostgreSQL + Redis

Transient:
  message.delta / progress.delta
  -> Redis Streams only
```

若需要严格保证数据库提交与 Redis 发布最终一致，再引入 `AgentEventOutbox` 和独立 Dispatcher，而不是直接把 PostgreSQL 事件删除或改为 Redis-only。

## 7. 相关代码与提交

- 事件流实现：`backend/apps/conversations/event_stream.py`
- 事件写入：`backend/apps/conversations/services.py::AgentRunService.append_event`
- SSE：`backend/apps/conversations/views.py::AgentRunEventStreamView`、`_sse`
- 配置：`backend/config/settings/base.py`、`.env.example`
- 测试：`backend/tests/test_event_stream.py`
- 本轮提交：`7413578`、`4c22bc8`、`818433c`、`4c75267` 及后续 correctness hardening 提交。
