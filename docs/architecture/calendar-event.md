# CalendarEvent 领域模型

CalendarEvent 使用 UUID 主键，并保存所有者、创建者、标题、描述、UTC 时间范围、原始
IANA 时区、位置、状态、可见性、重复规则、来源、外部 ID 和乐观锁版本号。

模型与数据库共同保证：

- `end_at` 晚于 `start_at`；
- `start_at`、`end_at` 必须是带明确时区的 datetime，保存前统一转换为 UTC；
- 本地事件没有外部 ID，非本地来源必须提供外部 ID；
- 同一用户、来源和外部 ID 只能对应一个事件；
- 版本号从 1 开始；
- `(user, start_at, end_at)` 和 `(user, status, start_at)` 具备查询索引。

`EventService` 是事件写入边界：创建、更新和取消均执行完整模型校验，按用户隔离数据，
并在事务行锁内校验 `expected_version` 后递增版本号。列表查询使用半开区间重叠语义
`start_at < starts_before && end_at > ends_after`。

模型层仍允许时间重叠；`EventService.detect_conflicts()` 负责确定性冲突检测，忽略取消
日程并支持排除正在编辑的事件。相邻的半开区间不视为冲突。

空闲时间搜索见 `planning.md`。REST API 的 PATCH/DELETE 要求 `expected_version` 查询
参数，过期版本返回 409；DELETE 表示取消而非物理删除。外部日历同步和前端 Calendar
页面属于后续独立任务。
