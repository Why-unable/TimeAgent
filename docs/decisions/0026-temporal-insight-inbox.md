# ADR 0026：Phase D 的确定性 Temporal Insight Inbox

## Context

主动能力不能由 Agent 产生一条建议就直接发送通知。系统需要先检测有证据的时间风险，再经过状态、去重、过期和用户处置，
晚报与通知才能消费同一事实。Phase D 当前只需要验证这一条确定性链路，不引入常驻主动 Agent。

## Decision

- 新增 `apps.insights` 与 `TemporalInsight` 业务模型，保存 kind、severity、evidence、deduplication key、expiry 和处置状态。
- `TemporalInsightService.scan` 当前检测未来 48 小时内截止或已逾期的未完成任务；扫描是幂等的，过期洞察不会继续出现在收件箱。
- `list_open` 是唯一收件箱读取边界；`act` 允许 snooze、dismiss、actioned 与显式 false-positive 四类确定性处置。
- false-positive 可选择禁用当前 kind。禁用写入用户偏好，同类洞察不再出现在收件箱或产生新投递；恢复开关后仍可重新展示未过期事实。
- Attention Policy 决定 `STORE`/普通/高优先通知，并遵守全局开关、kind 禁用、IANA 安静时间、每日配额和 cooldown。获准洞察由确定性 Celery 入口幂等物化为 `NotificationDelivery`，不调用 LLM。
- 同一 insight source/channel 只允许形成一条不可变 `NotificationDelivery`；后续扫描可以刷新洞察摘要，但不重写或重复发送既有投递。投递幂等键包含 payload schema 版本，升级时识别并保留旧键投递，避免因 deep-link、正文或调度时间变化产生冲突。
- dismiss、actioned 或 false-positive 会通过 `NotificationService` 取消仍处于 pending/queued/failed 的关联投递；已经 sending/sent 的投递不伪装成可撤销。
- Guardrail 以显式观察窗口计算 action、dismiss、delivery failure 与 false-positive rate；误报率以生成洞察数为分母，使未打断用户但在收件箱被标错的样本仍进入质量评测。
- Web/Capacitor 提供独立 `/insights/:insightId` 收件箱和通知 deep link；历史状态仍可按 ownership 读取。主操作按洞察 evidence 进入任务或规划页，用户也可把 insight id/title 带入 Time Steward，再由 `get_temporal_insight` Tool 读取服务端证据。
- Time Steward 的 list/get/act Tool 继续调用 `TemporalInsightService`；Agent 不运行 detector 规则、不替用户处置，也不从通知文案反推事实。

## Consequences

正面：检测、证据、注意力决策、通知取消和用户处置可测、可审计、可复用；代价是已物化通知不会随洞察摘要刷新，kind 级禁用仍较粗，且主动文案和 detector 仍需扩展。当前尚无真实用户 precision/recall 或通知观察窗口，不得宣称主动建议准确率。
