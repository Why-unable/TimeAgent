# ADR 0032：语义记忆分级授权与可撤销直接应用

- 状态：已接受
- 日期：2026-09-02

## 背景

M3.1-M3.3 对所有语义记忆写入执行用户确认，安全但会让“请记住……”产生重复授权。DeerFlow 的
Tool Mode 由主 Agent 直接 CRUD，交互轻但不能满足 TimeAgent 对排程影响、审计和撤销的要求。

## 决策

1. 后台提取、含糊表达和 `availability_constraint` 等高影响约束继续生成 pending Proposal。
2. 只有当前用户消息通过操作类型匹配的显式命令判定，且类别低风险、Policy 未发现敏感或指令型
   内容时，才成为直接应用候选。Agent 选择 Tool 或声明高 confidence 不能单独证明授权。
3. `TIME_MEMORY_AGENT_DIRECT_APPLY_MODE` 提供 `confirm`、`shadow`、`enabled` 三态发布门禁，默认
   confirm；内联 ActionProposal/HITL 开启时优先于直接应用。
4. 直接应用仍先创建 `MemoryProposal`，再由同一 `SemanticMemoryService` 事务应用，不提供 Agent
   直写 SemanticMemory 或 LangGraph Store 的路径。
5. Proposal 保存 applied memory ID/version 和是否实际改变业务状态。用户撤销时重新锁定并验证
   版本；后续已有变化时返回冲突，不覆盖新事实。
6. Create 撤销为软删除，Update 撤销恢复被替代记录并分配更高版本，Delete 撤销重新激活原记录。
   重复撤销幂等返回 undone。
7. 直接应用不扩大日历、任务或提醒权限。后续业务副作用继续遵循各自冲突、幂等和 HITL 规则。

## 备选方案

- 所有写入永久二次确认：安全但交互成本过高，不作为最终形态。
- 只要 Agent 调用 Tool 就直接写入：无法证明用户授权，且难以阻止注入内容，不采用。
- 直接物理删除或覆盖旧记录：无法可靠撤销和审计，不采用。
- 用前端实现撤销规则：会复制后端状态机并产生竞态，不采用。

## 影响与限制

- 新增 MemoryProposal 撤销审计字段、`undone` 状态、recent/undo API 和 Web 撤销入口。
- 自动化测试覆盖分级 Policy、三类撤销、幂等、冲突及用户隔离。
- 当前显式指令识别是保守确定性规则，不等于语义蕴含证明；未识别时安全降级为 pending。
- 当前规则只证明操作意图，不证明 Tool 的每个结构化参数都被原始消息逐字段蕴含；因此默认保持
  confirm，enabled 模式上线前必须补充参数一致性 Golden Set 和误写率验收。
- 2026-09-14 起，当前 Compose 按用户要求开启 Agent 低风险 Tool 的 enabled；后台 LLM 推断提取
  仍关闭，高影响约束仍要求确认。真实线上误写率和撤销率继续作为运行观测门禁。
- 聊天消息内嵌撤销按钮尚未实现，当前入口位于记忆设置页。
- 真实误写率、撤销率、用户中断率和 enabled 模式线上效果需要补测。
