# Time Steward 长期记忆

## 数据流

```text
事件/任务/提醒 API 或 Agent Tool
  -> Application Service
  -> PostgreSQL 业务事实 + ScheduleChange
  -> transaction.on_commit
  -> Celery time_memory.rebuild（5 秒防抖）
  -> 重新统计最近 180 天
  -> LangGraph PostgreSQL Store 中的用户画像
  -> Time Steward Middleware 按当前请求筛选并注入
```

简报定时任务直接进入 Briefing Workflow，不经过上述 Middleware，因此不会读取
Time Steward 的长期记忆。

## 存储边界

- 权威事实：`CalendarEvent`、`Task`、`Reminder`、`ScheduleChange`。
- 更新状态：`TimeMemoryRefreshState`，用于 dirty、processing、failed 和最近完成
  时间的监控。
- 派生画像：LangGraph Store namespace
  `("users", user_id, "time_memory")`，key 为 `profile`。
- 时间：数据库和画像时间均为 UTC；按用户 IANA 时区计算日期、星期和小时。

## 画像内容

- 7、30、180 个用户本地自然日窗口中的日程、任务、提醒与来源分布。
- 对跨天和重叠日程做区间并集后的总时长、日均/中位数、忙碌日、休息日、
  连续忙碌日、工作日/周末均值和高峰时段。
- 15 分钟创建 session、跨至少两个日期且不少于三项的批量规划、提前规划
  中位数、临近创建和长期提前创建比例。
- 改期、推迟、提前、取消和完成指标；当前事件模型没有完成状态时，事件完成率
  保持 `null`，不推断不存在的事实。
- 最近 180 天常用地点；至少三次、最近 90 天至少两次，评分后最多保留八个。
- 仅由 30 天与 180 天窗口共同支持的稳定规律；按自然周弱化，长期证据消失或
  连续三个有效周期无支持时过期。

## Agent 生命周期

- `before_agent` / `abefore_agent`：只从 Store 读取当前画像，不查询业务表、不重建。
- `wrap_model_call`：按近期负荷、长期习惯、规划方式、调整习惯、地点或普通规划
  分类，选择相关窗口、地点和稳定规律。
- Token 预算默认 800；运行时优先使用当前 LangChain 模型的 `get_num_tokens()`，
  不可用时才使用 LangChain 近似计数。候选项逐条加入，绝不截断 XML。
- `wrap_tool_call`：只有写工具成功返回后才设置 `schedule_changed=true`。
- `after_agent`：只在本轮确有成功写入时标记 dirty。Application Service 同时覆盖
  Web、Android、系统和未来外部日历入口。

## 防抖与失败

`TimeMemoryRefreshState` 使用 `clean / dirty / processing / failed`。用户从非 dirty
状态首次转为 dirty 时仅提交一个延迟任务；后续连续变化只更新 `dirty_at`。任务按
用户刷新状态行加锁，同一用户串行完整重算。计算或 Store 写入失败时保留上一版画像。
已知的 `schema_version=1` 会确定性迁移为 v2；未知或损坏的 schema 不会被注入，
下一次重建会从 PostgreSQL 事实生成当前 schema。

## 用户控制

- `GET /api/v1/time-memory/me/`：查看当前画像和刷新状态。
- `DELETE /api/v1/time-memory/me/`：清空当前画像并设置新的历史起点。
- `DELETE /api/v1/time-memory/me/places/{place_id}/`：主动遗忘地点并持续排除。
- `DELETE /api/v1/time-memory/me/patterns/{pattern_id}/`：主动遗忘稳定规律并持续排除。
- 偏好 `time_memory_enabled=false`：停止生成、读取和注入。
- `time_memory_allow_generation=false`：停止生成并删除派生画像。
- `time_memory_allow_context_injection=false`：保留生成，但不提供给 Time Steward。

## 运维

迁移并初始化 LangGraph Store 后，可手动重建：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec django python manage.py rebuild_time_memory

docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec django python manage.py rebuild_time_memory --user-id <USER_ID>
```

排查失败任务：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec django python manage.py shell -c \
  'from apps.time_memory.models import TimeMemoryRefreshState; print(list(TimeMemoryRefreshState.objects.exclude(status="clean").values()))'
```

用户偏好 API 支持：

- `time_memory_enabled`
- `time_memory_allow_generation`
- `time_memory_allow_context_injection`

简报工作流不加载 Time Steward 画像，也不会触发上述 Agent middleware。
