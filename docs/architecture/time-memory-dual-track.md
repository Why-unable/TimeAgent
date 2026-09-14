# TimeAgent 双路线记忆设计

## 文档状态

- 状态：M1 已实现，M2 部分实现，M3.1/M3.2/M3.3/M3.4 已实现但默认保持确认模式；待真实环境与评测验收
- 行为记忆路线：已实现
- 语义记忆路线：已实现受控提取、Policy、审批、版本化持久化和 Agent 上下文回注；默认关闭
- 已实现可重建的 LangGraph Store 语义记忆投影任务；尚未实现专用召回检索和真实评测基线
- LangChain 官方文档核对日期：2026-08-31

## 设计结论

TimeAgent 的长期记忆应由两条来源并行构成，但必须保持来源、可信度和更新方式的边界：

```text
业务事实 ──→ 行为记忆（确定性计算）
用户明确表达 ──→ 语义记忆（LLM 提议 + Policy 审核）
```

两条路线都只能作为受控决策输入，不能绕过权限、幂等、版本和审计机制。

## LangChain 官方能力与项目选型

LangChain 官方将 Thread 内历史定义为短期记忆，将跨 Thread 的用户或应用数据定义为长期记忆。长期记忆通过 LangGraph Store 以 `namespace + key + JSON document` 组织；写入可以发生在主请求 hot path，也可以由后台任务异步完成。官方还区分两种语义记忆组织方式：

- **Profile**：持续更新一个完整 JSON 画像，统一但容易在大对象更新时误覆盖字段；
- **Collection**：每条记忆是独立文档，新增更安全、召回率通常更高，但需要额外处理去重、冲突、更新和删除。

参考：

- [LangChain Long-term memory](https://docs.langchain.com/oss/python/langchain/long-term-memory)
- [LangChain Memory overview](https://docs.langchain.com/oss/python/concepts/memory)
- [LangGraph Memory](https://docs.langchain.com/oss/python/langgraph/add-memory)

TimeAgent 采用组合方案：

| 记忆类型 | 组织方式 | 权威存储 | 使用方式 |
|---|---|---|---|
| 行为记忆 | 单个版本化 `TimeMemoryProfile` | PostgreSQL 业务事实；Store 中的 Profile 可重建 | 确定性重建、按意图裁剪 |
| 语义记忆 | 多条类型化 Memory Collection | PostgreSQL `SemanticMemory` 表 | 按类别精确召回，必要时投影到 LangGraph Store |
| 对话短期记忆 | Thread State / Messages | LangGraph Checkpoint | 多轮连续性和摘要 |

第一版不引入 Deep Agents 文件记忆、独立向量数据库或可自主改写记忆的 Memory Agent。它们与当前事务系统、用户可见审计和删除要求不匹配，也超出当前项目边界。

## 路线一：行为记忆

### 数据来源

当前实现从 PostgreSQL 业务数据构建记忆，来源包括：

- 日历事件；
- 任务；
- 提醒；
- `ScheduleChange` 日程变更记录；
- `TaskExecutionSignal` 任务执行信号。

来源加载由 `backend/apps/time_memory/source_repository.py` 完成。

### 构建方式

`TimeMemoryAnalyzer.build_profile()`（`backend/apps/time_memory/analyzer.py`）以 7/30/180 天窗口确定性计算：

- 常用地点；
- 日程和工作时间分布；
- 规划风格；
- 重排、取消和修改模式；
- 任务预估时长与实际执行时长校准；
- 稳定行为模式；
- 样本量和置信度。

它不调用 LLM，也不读取 `Conversation`、`AgentRun` 或历史聊天消息。Profile 是业务事实的派生数据，可以随时重建，不能替代业务数据库。

业务变化通过 `record_schedule_change()` 或 `mark_time_memory_dirty()` 标记刷新状态，由 Celery 延迟合并后调用 `TimeMemoryUpdater.rebuild()`。重建结果写入 LangGraph Store 的用户隔离命名空间。

### 当前使用方式

`TimeMemoryMiddleware` 在 Agent 运行开始时读取 Profile，再根据当前请求意图和 Token Budget 选择性注入模型上下文。当前行为记忆主要作为 Prompt 上下文使用，规划服务尚未全面消费类型化记忆特征。

## 路线二：语义记忆

### 解决的问题

业务数据能够反映用户实际做了什么，但无法完整记录用户明确表达的长期偏好，例如：

- “周五下午尽量不要安排会议”；
- “深度工作最好连续两个小时”；
- “出差时不要安排早于九点的日程”。

这些信息不一定会立即体现在日历、任务或执行信号中，需要从用户明确表达或纠正中提取。

### 推荐架构

LLM 不应直接修改长期 Profile，而应只生成结构化记忆提议：

```text
当前用户请求 / 明确纠正
  → Memory Extraction LLM
  → MemoryProposal
  → Memory Policy
  → 去重、冲突、敏感信息和置信度检查
  → 自动写入或请求用户确认
  → Memory Service 持久化与审计
```

语义记忆的 PostgreSQL 记录是权威事实；LangGraph Store 即使使用 PostgreSQL 后端，也只作为 Agent 召回接口或派生投影，不能成为绕过 Application Service 的第二写入口。

示例：

```json
{
  "operation": "upsert",
  "category": "scheduling_preference",
  "key": "friday_afternoon",
  "value": {"avoid_meetings": true},
  "confidence": 0.96,
  "evidence": "用户明确表达长期偏好"
}
```

### LLM 的职责

- 识别是否存在长期可复用偏好；
- 选择受限的记忆类别；
- 提取结构化字段；
- 给出置信度和证据引用；
- 提议新增、更新或删除操作。

### 后端 Policy 的职责

- 判断是否允许进入长期记忆；
- 过滤敏感信息、短期闲聊和模型私有推理；
- 检测现有记忆冲突；
- 应用置信度和最小样本门槛；
- 实现去重、版本、幂等、过期和撤销；
- 判断是否需要用户确认；
- 记录来源、审计和实际使用位置。

高影响偏好、删除操作和可能改变未来排程的规则，默认应采用 Observe/Suggest 或 HITL，而不是静默写入。

## 语义记忆数据模型

### `SemanticMemory`

建议新增 PostgreSQL 业务表，核心字段如下：

| 字段 | 作用 |
|---|---|
| `id` | UUID 主键 |
| `user_id` | 用户隔离边界 |
| `category` | 受限类别，例如 `scheduling_preference`、`availability_constraint` |
| `key` | 类别内稳定标识，例如 `friday_afternoon_meetings` |
| `value` | 经 Pydantic 校验的类型化 JSON，不保存任意自由文本 |
| `status` | `active/superseded/deleted` |
| `source_type` | `explicit_user/background_extraction/user_edit` |
| `source_run_id` | 可选，指向产生提议的 Agent Run |
| `confidence` | 提取置信度；用户确认后不再把它当作用户意愿置信度 |
| `version` | 乐观并发版本 |
| `valid_from/expires_at` | 生效与过期边界 |
| `created_at/updated_at/deleted_at` | 审计时间 |

建议对 `(user_id, category, key, status=active)` 建立条件唯一约束。更新和删除必须携带 `expected_version`，由 Application Service 在事务中完成。原始对话已经保存在 Conversation/AgentRun 中，记忆表只保存必要的来源引用或受限证据摘要，避免复制整段敏感对话。

### `MemoryProposal`

LLM 只能输出并提交提议，不直接写 `SemanticMemory`：

```python
class MemoryProposalPayload(BaseModel):
    operation: Literal["create", "update", "delete", "ignore"]
    category: SemanticMemoryCategory
    key: str
    value: dict[str, JsonValue]
    confidence: float = Field(ge=0, le=1)
    evidence_excerpt: str
    reason_code: MemoryReasonCode
```

`evidence_excerpt` 只用于 Policy 验证它是否确实来自本轮用户消息，持久化时优先保存 `source_run_id` 和服务端计算的证据 hash，不复制整段对话。持久化 Proposal 还需要 `pending/approved/rejected/applied/expired` 状态、模型配置标识、Schema 版本、幂等键和 Policy 决策原因。不得保存模型私有推理或原始 hidden reasoning。

## 提取与写入调用链

### 后台提取主链路

官方文档同时支持 hot path 和后台写入。TimeAgent 第一版应以 Celery 后台提取为主，避免增加聊天响应延迟并合并连续对话：

```text
AgentRun completed
  → transaction.on_commit(enqueue extraction)
  → Celery MemoryExtractionTask(run_id)
  → 读取当前用户消息 + 有界的必要上下文
  → Structured Output LLM
  → Pydantic 校验 MemoryProposalPayload
  → MemoryPolicy.evaluate()
  → ignore / pending confirmation / apply
  → SemanticMemoryService
  → PostgreSQL transaction
  → 刷新 LangGraph Store 投影（如启用）
```

提取输入默认只包含本轮用户消息和解决指代所需的少量相邻消息；不得把完整 Checkpoint、工具内部结果、系统提示词、摘要模型输出或模型私有推理交给记忆提取模型。

### 用户显式操作链路

当用户明确说“记住……”“修改我的偏好……”或“忘掉……”时，可由 Time Steward 调用受限 Tool，但调用链仍必须是：

```text
Memory Tool
  → SemanticMemoryApplicationService
  → Memory Policy
  → ActionProposal/HITL（需要时）
  → Repository
  → PostgreSQL
```

Tool 不得直接访问 ORM 或 LangGraph Store。删除默认使用可审计软删除；用户执行彻底重置时，再由独立管理 Service 清理语义记忆和 Store 投影。

## 模型与 LangChain 技术选择

- 使用现有 Provider Factory 创建独立的 `memory_extraction_model` 配置，不复用 Time Steward 的工具循环；
- 使用 LangChain 结构化输出能力生成 Pydantic Schema，模型只进行一次有界提取，不构建新的多步 Agent；
- 设置独立的 timeout、模型重试和最大输出 Token；温度保持 `0`；
- 对 OpenAI-compatible 与 Anthropic 分别做 Schema 兼容测试；若原生结构化输出不可用，采用当前项目已有的 Tool Strategy；
- 使用 Celery 实现后台形成和有限重试；业务幂等由 Service 保证，不能依赖 Celery exactly-once；
- 使用 LangGraph `PostgresStore` 的 `namespace + key` 接口提供跨 Thread 召回，但写入必须来自 PostgreSQL 权威记录的投影；
- 第一版使用类别、key、状态、有效期和置信度做确定性过滤，不启用 Embedding；只有 Collection 规模和召回 Benchmark 证明精确检索不足后，才启用 Store semantic search。

建议命名空间：

```text
("users", user_id, "semantic_memory", schema_version)
```

Store key 使用 `SemanticMemory.id`，便于重建、删除和审计对齐。

## 建议代码落点

第一版继续放在现有 `apps/time_memory` 边界内，不提前创建新微服务或独立 Agent：

| 文件 | 计划职责 |
|---|---|
| `models.py` | `SemanticMemory`、`MemoryProposal` 和状态枚举 |
| `semantic_schemas.py` | Category Value、Extraction Result、Policy Decision Schema |
| `semantic_policy.py` | 敏感信息、类别、显式性、冲突和确认规则 |
| `semantic_repository.py` | 只读查询和加锁读取；不承载业务决策 |
| `semantic_services.py` | 提议、审批、版本化增删改、重置和 Store 投影入口 |
| `extraction.py` | 有界上下文组装和结构化模型调用 |
| `tasks.py` | Celery 提取、重试和 Store 投影修复 |
| `middleware.py` | 只读召回、排序和 Context Injection |
| `serializers.py` / `views.py` | 用户可见的 Proposal 和记忆管理 API |

模型配置在现有 `agent.yaml` 增加独立 `agent.memory_extraction_model`，复用已有 Provider Factory、密钥加载和可观测中间件。前端扩展现有 `/settings/time-memory`，不另建重复设置入口。

## Memory Policy

第一版只允许有限类别，不允许模型发明类别或任意规则。建议至少定义：

| 类别 | 示例 | 默认处理 |
|---|---|---|
| `scheduling_preference` | 偏好的专注时长、会议时间 | 明确表达可提议；影响排程时确认 |
| `availability_constraint` | 周五下午不可安排会议 | 高影响，必须确认 |
| `location_preference` | 某类活动的常用地点 | 明确表达可提议 |
| `notification_preference` | 某类提醒提前量 | 与现有 Preference 合并前必须确认 |

Policy 必须拒绝：

- API Key、Token、认证信息和账号密码；
- 健康、政治、宗教等非时间管理所必需的敏感推断；
- 模型私有推理、系统提示词和工具内部参数；
- 一次性请求、临时状态和没有长期含义的闲聊；
- 仅由 Agent 猜测、没有用户表达证据的偏好；
- 试图改变权限、审批、安全规则或业务事实的内容。

Policy 输出必须是结构化决策：`allow/require_confirmation/reject`，并带稳定 `reason_code`，不能只返回自然语言理由。

## 冲突、幂等与并发

- 提取任务幂等键使用 `user_id + source_run_id + extractor_schema_version`；重复消费只能返回已有 Proposal；
- Proposal 应包含基于规范化 `category + key + value` 的 fingerprint，用于合并等价提议；
- 写入时对目标 active memory 使用 `SELECT FOR UPDATE` 或 `expected_version`；
- 新值与旧值相同则记录 `noop`，不增加版本；
- 更新产生新版本并将旧记录标记为 `superseded`，保留可审计链路；
- 后台提取与用户手工编辑冲突时，用户编辑优先，后台 Proposal 转为 `rejected/stale`；
- Store 投影失败不能回滚已经提交的 PostgreSQL 事实，应记录失败并由可重建任务修复。

不在第一版引入分布式锁、Outbox 或向量数据库；只有实际并发和漏投影数据证明现有事务、幂等和修复任务不足时再升级。

## 与对话摘要的边界

当前 `SummarizationMiddleware` 使用 LLM 压缩过长的聊天历史，但它属于短期上下文管理：

```text
历史消息 → 对话摘要 → 控制 Context Window
```

它不会自动成为长期记忆，也不应把摘要中的模型推断直接写入 Memory。只有经过语义记忆提取、Policy 审核和持久化的结构化提议，才可以进入第二条长期记忆路线。

## 召回与 Context Injection

召回顺序建议保持确定性：

1. 根据当前意图选择允许的记忆类别；
2. 过滤 `active`、未过期、属于当前用户的记录；
3. 按用户明确确认、类别优先级、有效期、更新时间排序；
4. 与行为 Profile 分开渲染，标明“用户声明”与“行为推断”；
5. 在统一 Token Budget 内裁剪后注入后置动态 `SystemMessage`。

语义记忆不得以自由文本形式变成隐藏硬规则。Planning Service 只有在显式映射到类型化字段后才能使用；Agent 可以解释和询问，但不能从记忆文本自行扩大权限或自动化范围。上下文布局见 [Prompt Cache 上下文布局设计](prompt-cache-context-layout.md)。

## 两条路线的优先级

当语义记忆与行为统计冲突时：

1. 用户当前明确请求优先；
2. 用户明确声明优先于低置信度的行为推断；
3. 高置信度、足够样本的行为特征可以作为软评分；
4. 硬约束、权限和审批规则永远高于两类记忆。

语义记忆不应直接覆盖原始业务事实。例如用户声称“我从不在周五开会”，不能修改历史日历事件，只能作为未来规划偏好提议。

## 分阶段实施计划

### Phase M0：契约与离线评测

- 创建 ADR，确定 PostgreSQL 权威表、Store 投影和后台提取边界；
- 定义受限 Category、Value Schema、Proposal、PolicyDecision 和 reason code；
- 建立脱敏 Golden Set，覆盖 create/update/delete/ignore、指代、冲突、敏感信息和 Prompt Injection；
- 实现无持久化副作用的离线 Extractor，记录 Schema Validity、Operation Accuracy、Precision/Recall/F1 和 Token/Task。

验收：Schema、Policy 和评测可以独立运行；不连接生产写入。真实指标需要补测。

### Phase M1：只建议，不自动写入

- 增加 `SemanticMemory`、`MemoryProposal`、迁移、Repository 和 Application Service；
- AgentRun 完成后通过 Celery 后台提取；
- 所有有效 Proposal 进入 `pending`，在 Web/Android 记忆管理页由用户确认、编辑或拒绝；
- 增加列表、详情、审批、编辑、删除 API，并重新生成 OpenAPI 和前端类型；
- 增加模型调用、Policy 决策、队列失败和用户处置审计。

验收：没有确认就不会影响 Agent 或规划结果；重复任务不产生重复 Proposal；用户可以查看来源并撤销。

### Phase M2：确认后召回

- 将已确认语义记忆投影到 LangGraph Store Collection；
- 在 `TimeMemoryMiddleware` 中按类别召回，与行为 Profile 分区渲染；
- 接入后置动态 `SystemMessage` 和统一 Token Budget；
- 增加无 Store、投影陈旧和 Profile 冲突时的降级逻辑；
- 做 Memory on/off 消融，验证任务成功率、Tool 参数正确率、Token 和延迟变化。

验收：关闭语义记忆时行为与当前版本一致；Store 故障不影响业务写入；错误用户之间无召回泄漏。

### Phase M3：受控快捷写入与可选语义检索

- 为“记住/修改/忘记”增加受限 Tool，并复用 Application Service 与 HITL；
- 仅对低风险、用户明确表达且 Policy 允许的类别评估自动接受，默认仍保持确认；
- 当精确类别检索的 Benchmark 明确不足时，再给 PostgresStore 配置 Embedding 索引；
- 增加记忆过期、合并、批量重建和 Store 投影修复任务。

验收：语义检索必须相对 exact/filter Baseline 提升召回且不显著提高错误注入率；否则保持关闭。

## DeerFlow Memory Tool 调研与 TimeAgent 落地方案

### 调研范围与结论

本节基于 2026-08-31 本机父目录 `deer-flow` 当前代码调研，主要证据包括：

- `config.yaml` 与 `config.example.yaml` 的 `memory.enabled / mode / manager_class / backend_config`；
- `deerflow/config/memory_config.py` 的 `MemoryConfig` 与 `should_use_memory_tools()`；
- `deerflow/agents/memory/tools.py` 的四个 LangChain Tool；
- `deerflow/agents/factory.py`、`deerflow/agents/lead_agent/agent.py` 的 Tool 注册逻辑；
- `deerflow/agents/lead_agent/prompt.py` 的 Tool 使用约束；
- `deerflow/agents/memory/manager.py` 与 DeerMem backend 的持久化接口；
- `backend/tests/test_memory_tools.py` 的 Tool、用户隔离、去重和模式切换测试。

DeerFlow 当前本机实际配置为 `memory.enabled: false`、`memory.mode: middleware`，因此当前运行配置没有启用 Memory Tool。`config.example.yaml` 和代码支持实验性的 `mode: tool`，不能把“代码支持”描述成“当前已启用”。

DeerFlow 所谓的 Memory ToolNode 并不是项目手写的独立 LangGraph 节点。实际做法是：

```text
config memory.mode=tool
  → should_use_memory_tools()
  → get_memory_tools()
  → memory_search / memory_add / memory_update / memory_delete
  → 注册到 LangChain create_agent(tools=...)
  → create_agent 内置 Agent ↔ Tools 循环执行
  → Tool 调用 MemoryManager
  → 具体 backend 完成检索或持久化
```

也就是说，ToolNode 属于 `create_agent()` 生成的内部运行图。DeerFlow 自研部分主要是 Tool Schema、运行时作用域、Manager 接口、backend、模式切换和系统提示，而不是重新实现一套 ToolNode。

### DeerFlow 的关键实现

| 机制 | DeerFlow 实现 | 解决的问题 | 当前边界 |
|---|---|---|---|
| 模式开关 | `memory.mode=middleware/tool` | 后台自动形成与模型主动 CRUD 二选一 | 个别 backend 可声明 tool 模式仍保留被动写入 |
| Tool 注册 | Agent Factory 将四个 Tool 加入 `create_agent()` | 复用标准 Tool Calling 循环 | `enabled=false` 时不注册 |
| 作用域 | 从可信 Runtime 解析 `user_id` 和 `agent_name` | 避免模型自行指定用户 | 依赖所有调用链正确传播 Runtime Context |
| 存储抽象 | Tool 只调用 `MemoryManager`，backend 实现 CRUD/search | 支持 DeerMem、Mem0、Honcho 等替换 | backend 不支持某操作时返回结构化错误 |
| Search | `memory_search(query, category, limit)` | Tool 模式按需召回，避免全量注入 facts | DeerMem 使用 FTS5，失败回退 substring |
| Add | 写入前做空值与重复内容检查，backend 再做权威并发检查 | 减少重复事实和无效写入 | 模型仍然决定内容、类别和 confidence |
| Update/Delete | 先 search 获得 `fact_id`，再按 ID 修改或删除 | 避免模糊匹配错误修改 | Tool 模式不经过自动提取的 scope gate |
| 上下文策略 | Tool 模式只自动注入全局摘要，agent facts 留给 search | 避免同一 facts 自动注入和 Tool 返回两次 | 是否 search 依赖模型行为 |
| Prompt 约束 | 系统提示要求相关时先 search、近重复优先 update | 改善模型 Tool 选择 | 提示不是权限或事务边界 |
| 测试 | 覆盖注册互斥、重复、Runtime scope、unsupported backend | 验证 Tool 协议与 Factory 装配 | 是否提升任务效果仍需 Eval 证明 |

### 对 TimeAgent 的判断

TimeAgent 可以复用 DeerFlow 的四点：

1. 使用标准 LangChain `@tool`，直接注册到现有 `create_agent()`，不另建重复 ToolNode。
2. 用户身份、AgentRun、Tool Call ID 和幂等键只能来自可信 `ToolRuntime`。
3. Search 与 Write Tool 分开；修改和删除必须先取得稳定的 memory ID。
4. Tool 只依赖 Application Service，不访问 ORM 或 LangGraph Store。

但不能直接复制 DeerFlow 的“模型调用 Tool 后立即写入事实”。TimeAgent 的语义记忆会影响未来排程、通知和时间约束，且仓库规范要求长期 Memory 写入经过 Memory Policy、高风险写操作经过审批。因此 TimeAgent 应采用 **Tool 生成 Proposal、用户确认后生效**，而不是模型直接 CRUD 权威记录。

### 推荐 Tool 设计

第一版增加四个 Tool，放入 `apps/agents/tools/memory_tools.py`：

| Tool | 类型 | 输入 | 实际效果 |
|---|---|---|---|
| `search_time_memories` | 只读 | `query?`、`category?`、`limit` | 从当前用户 active semantic memory 中返回有界结果 |
| `remember_time_preference` | 写提议 | `category`、类型化 `value` | 创建 `operation=create` 的 `MemoryProposal` |
| `update_time_preference` | 写提议 | `memory_id`、类型化变更值 | 创建 `operation=update` 的 `MemoryProposal` |
| `forget_time_preference` | 写提议 | `memory_id` | 创建 `operation=delete` 的 `MemoryProposal` |

TimeAgent 不需要复制 DeerFlow 的 `memory.mode=middleware/tool` 互斥开关，因为两条入口在本项目中是互补关系。建议沿用现有 Django 功能开关：

```text
TIME_MEMORY_AGENT_SEARCH_TOOL_ENABLED=false
TIME_MEMORY_AGENT_WRITE_TOOLS_ENABLED=false
TIME_MEMORY_AGENT_INLINE_APPROVAL_ENABLED=false
```

Search 和 Write 分开发布：先开启只读 Search，再在审批、版本冲突和 Eval 完成后开启 Write Proposal Tool。模型选择和提取模型仍由 `agent.yaml` 管理，功能发布开关由 Django Settings 管理，避免把业务安全策略混入模型配置。

不允许 Tool 接收 `user_id`、`source_run_id`、`confidence`、`status`、`idempotency_key` 或任意 evidence。它们分别由可信 Runtime、当前 AgentRun、服务端规则和 Tool Call ID生成。模型可以提出“记住什么”，不能自行声明“已经获得用户确认”或给自己提高置信度。

调用链固定为：

```text
Time Steward create_agent
  → LangChain 内置 Tools 节点
  → memory_tools.py
  → require_actor / require_writable
  → SemanticMemoryToolService
  → MemoryPolicy
  → SemanticMemoryService.create_proposal()
  → PostgreSQL MemoryProposal(pending/rejected)
  → 用户确认
  → SemanticMemoryService.decide_proposal()
  → PostgreSQL SemanticMemory
  → on_commit Store 投影
```

默认关闭内联审批时，`remember/update/forget` 的成功返回为：

```json
{
  "proposal_id": "...",
  "status": "pending",
  "requires_confirmation": true
}
```

不能返回“已记住”或“已删除”，因为此时权威记忆尚未改变。Agent 最终回答也必须使用“已提交记忆确认”，避免造成已执行错觉。

开启 `TIME_MEMORY_AGENT_INLINE_APPROVAL_ENABLED=true` 后，三个写 Tool 会先由 LangChain
`HumanInTheLoopMiddleware` 中断。用户批准并恢复同一 AgentRun 后，Tool 才创建并立即批准
`MemoryProposal`，成功返回 `status=applied`、`requires_confirmation=false`。用户拒绝时 Tool
不会执行；Agent 在得到 `applied` 前仍不得声称记忆已经生效。

### Policy、审批与并发

- `search_time_memories` 进入 `READ_ONLY_TOOLS`，其他三个进入 `WRITE_TOOLS`，自动复用现有 `ToolAuditMiddleware`。
- 写 Tool 使用 `tool_idempotency_key(runtime, purpose=...)`，同一个 Tool Call 重试只生成一个 Proposal。
- `memory_id` 查询必须带当前 `user` 条件，跨用户 ID 统一返回不存在。
- Service 在事务内锁定目标 active memory；Update/Delete Proposal 保存目标 memory ID 和目标版本。
- 用户批准时再次检查版本；若记忆已经更新、删除或过期，将 Proposal 标记为 stale/conflict，而不是覆盖新事实。
- 第一版所有 Tool 写提议都需要用户确认。是否允许“用户在本轮明确说记住”自动接受，必须经过独立 Benchmark 和安全评审后再决定。
- Tool 输入仍要经过当前 `MemoryPolicy` 的类别、敏感信息和 Value Schema 校验；Tool 模式不能绕过后台提取链路已有的安全门。

### 与后台提取的关系

TimeAgent 不采用 DeerFlow 默认的 middleware/tool 二选一，而采用职责互补：

```text
后台提取：发现用户可能长期有用、但没有显式发出记忆命令的偏好
Agent Tool：处理“记住这个 / 改成这样 / 忘掉它”等明确即时意图
共同出口：MemoryProposal → Policy → 确认或受控直接应用 → SemanticMemory
```

两条路径必须复用同一个幂等和近重复检测。若后台任务与 Tool 对同一 `category + key + value` 同时提议，只保留一个 pending Proposal，并把来源记录为多个触发证据，而不是向用户展示两次确认。

### 分步实施与验收

#### M3.1：只读 Search Tool

实现状态：已实现，默认由 `TIME_MEMORY_AGENT_SEARCH_TOOL_ENABLED=false` 关闭。

- 增加 `search_time_memories` 和有界 exact/category 检索；
- 接入 `READ_ONLY_TOOLS`、Tool Audit 和 Agent Prompt；
- 验证用户隔离、过期过滤、输出裁剪和无结果行为。

验收：查询不会访问其他用户数据；关闭上下文注入时仍可显式 search；Tool 结果不包含 evidence hash、内部 Policy 字段或完整来源对话。

#### M3.2：Proposal Write Tools

实现状态：已实现，默认由 `TIME_MEMORY_AGENT_WRITE_TOOLS_ENABLED=false` 关闭。

- 增加 remember/update/forget 三个 Tool；
- 抽出 `SemanticMemoryToolService` 组装服务端字段；
- 扩展 Proposal 保存 `target_memory_id`、`target_version` 和 Tool 来源；
- 接入现有审批页，并让 Agent 对 pending 状态给出准确反馈。

当前代码已经完成 Tool、Service、Proposal 来源、目标 memory/version、审批前版本复核和系统提示；“编辑后接受”仍未实现，继续使用接受或拒绝两种处置。

验收：Tool 调用后 active memory 不变化；批准后才变化；拒绝、重复调用、并发更新和跨用户 ID 均有固定测试。

#### M3.3：对话内 HITL 恢复

实现状态：已实现，默认由 `TIME_MEMORY_AGENT_INLINE_APPROVAL_ENABLED=false` 关闭。

- 三个 Memory 写 Tool 已进入高风险策略表，只允许 approve/reject；
- `HumanInTheLoopMiddleware` 在 Tool 执行前中断，`ActionProposal` 持久化审批事实；
- 恢复后由 `ToolAuditMiddleware` 将临时审批绑定到真实 Tool Call ID 并标记 executing；
- `SemanticMemoryToolService` 只接受当前用户、当前 AgentRun、当前 Tool Call 且完整参数与审批快照一致的已批准执行；
- ActionProposal 保存目标 memory ID/version 快照，Tool 真正执行前重新读取权威表验证；
- 快照过期时 ActionProposal 标记 failed，Tool 返回可恢复错误，不创建 MemoryProposal；
- 验证通过后仍复用 `MemoryPolicy → MemoryProposal → SemanticMemoryService`，不提供绕过 Policy 的直接写入口。

两种写入模式都保留：内联审批关闭时生成 pending MemoryProposal 并进入记忆管理页；开启时
由聊天中的 ActionProposal 完成一次审批，恢复后的 MemoryProposal 直接应用，避免要求用户对同一
动作确认两次。

自动化测试已覆盖无审批直接调用拒绝、同一 AgentRun 中断/批准/恢复/一次生效，以及审批后目标
版本变化时拒绝写入。重复确认、持久化恢复和 Tool Call 幂等继续复用 ActionProposal、Checkpoint
和 ToolAudit 的现有测试。真实 PostgreSQL Checkpoint + Celery Worker 重启验收尚未执行，不能写成
生产验证完成。

#### M3.4：审批摩擦与分级自动接受

实现状态：已实现，默认 `TIME_MEMORY_AGENT_DIRECT_APPLY_MODE=confirm`，因此当前生产配置仍保持
二次确认。该开关还支持 `shadow` 和 `enabled`：Shadow 会以
`shadow_direct_apply_candidate` 记录候选但继续确认；Enabled 才允许通过 Policy 的显式低风险指令
直接应用。若 `TIME_MEMORY_AGENT_INLINE_APPROVAL_ENABLED=true`，内联 HITL 优先，直接应用模式不会
绕过已经建立的 ActionProposal。

目标不是复制 DeerFlow 的模型自主直接 CRUD，而是把**用户明确记忆指令本身视为可验证的授权
信号**。低风险且无歧义的操作直接生效并允许撤销；推断、高影响、冲突和含糊操作继续确认：

| 场景 | 目标处置 | 原因 |
|---|---|---|
| 用户明确说“请记住……”且内容属于低风险允许类别 | 直接应用，展示“已记住 · 撤销” | 避免对同一明确意图二次确认 |
| 用户明确修改一条目标唯一、版本未变化的低风险偏好 | 直接应用，可撤销 | 用户意图和目标都明确 |
| 用户明确忘记一条目标唯一的记忆 | 软删除并提供撤销 | 删除有明确授权，同时保留恢复能力 |
| 后台从普通对话推断出的偏好 | pending，可集中批量确认 | 用户没有发出记忆命令，模型可能过度推断 |
| `availability_constraint` 等会显著影响未来排程的硬约束 | 保留 HITL | 误写可能持续排除可用时间 |
| 目标不唯一、与现有记忆冲突或审批期间版本变化 | 澄清或重新确认 | 防止修改错误对象或覆盖新事实 |
| 敏感内容、系统指令、Tool 输出或 Prompt Injection | 拒绝 | 不能通过降低交互摩擦绕过安全边界 |

“显式指令”不能只由 Agent 是否选择了 Tool 或模型给出的 `confidence=1.0` 证明。当前服务端会校验
本轮原始用户消息是否包含与 create/update/delete 对应的明确命令，并继续校验允许类别、当前目标
和版本；用户、Run、Tool Call ID 和完整参数来自可信 Runtime 与 ActionProposal/ToolAudit 链路。
当前确定性规则还不能证明每个 Tool 参数都被自然语言逐字段蕴含，因此默认保持 `confirm`；未通过
操作意图校验时降级为 pending。启用 `enabled` 前，还需要用 Golden Set 验证参数一致性和误写率。

低风险记忆直接生效也不能扩大业务权限。记忆只是未来规划的受控输入；根据记忆创建、移动或取消
日程时，仍必须遵循日历冲突、权限和 ActionProposal 规则。记忆授权与业务副作用授权是两件事。

已实现的发布顺序：

1. Shadow 模式只记录“理论上可直接应用”的 Policy 结果，实际仍保持确认，统计用户接受、编辑、
   拒绝和撤销情况；
2. 先开放明确低风险 Create，并提供即时撤销和审计记录；
3. 再开放目标唯一的 Update/Delete；
4. 后台推断、高影响约束和冲突操作继续确认，不随低风险路径一起放开。

代码已将 `MemoryPolicyDecision` 扩展为 `apply / require_confirmation / reject`，并增加：

- `ExplicitMemoryIntent` 对 create/update/delete 使用不同的保守显式命令规则，否定指令不授权；
- 敏感内容与 Prompt Injection 特征在直接应用判断前拒绝；
- `MemoryProposal` 保存实际变更的 memory ID、版本、是否改变事实与撤销时间；
- 撤销在 PostgreSQL 事务中锁定 Proposal 和 Memory，版本变化或出现更新记录时返回冲突；
- Create 撤销执行软删除，Update 撤销恢复上一版本，Delete 撤销重新激活原记录；
- 最近七天直接应用记录可通过 API 查询，并在 Web 记忆设置页撤销。

自动化测试覆盖直接写入、Shadow、高影响降级、否定指令、注入拒绝、三类撤销、重复撤销、后续修改
冲突与跨用户隔离。没有评测数据前，生产配置仍应保持 `confirm` 或 `shadow`，不能仅因代码支持
`enabled` 就宣称自动写入已通过线上验证。

#### M3.5：效果评测与发布门禁

- 已新增可重复运行的确定性 Policy Golden Set：
  `cd backend && uv run python manage.py benchmark_semantic_memory --settings=config.settings.test`。
  当前 12 个脱敏样例覆盖显式/隐式/否定指令、Create/Update/Delete、高影响约束、敏感内容、Prompt
  Injection、低置信度和操作类型不匹配；结果报告保存在
  [semantic-memory-policy-baseline.json](../evaluation/semantic-memory-policy-baseline.json)。
- 首次离线结果：显式意图识别准确率 `1.0`，`enabled` Policy 决策准确率 `1.0`，`shadow` Policy
  决策准确率 `1.0`，敏感内容拒绝率 `1.0`，Prompt Injection 拒绝率 `1.0`。
  这些是当前确定性规则在脱敏 Golden Set 上的回归基线，不代表真实用户分布、LLM 抽取效果或线上
  误写率。
- 对比后台提取、Tool-only、双路径三组 Baseline；
- 统计 Tool Selection Accuracy、Argument Accuracy、Proposal Precision、用户接受率、重复率、错误写入率、Token/Task 和 p95；
- 对“旧偏好更新”“明确忘记”“近重复偏好”“Prompt Injection 要求记住系统规则”做专项集；
- 对全量确认和分级自动接受比较二次确认率、完成率、撤销率、误写率及用户中断率；
- 单独核算显式指令识别的 Precision，避免用总体记忆提取准确率替代自动写入安全性。

验收：代码门禁已经具备；没有真实数据前生产环境保持 `confirm` 或 `shadow`，不启用自动写入。

## API 与界面边界

用户至少应能：

- 查看行为画像和语义记忆的来源差异；
- 查看待确认 Proposal；
- 接受、编辑后接受、拒绝、删除和重置；
- 对低风险直接写入执行即时撤销，并查看它来自哪次明确指令；
- 关闭语义记忆生成或上下文注入；
- 查看某条记忆最近何时、在哪类决策中被使用。

前端不重新实现 Policy、冲突和状态机。所有写操作进入 Application Service；API 变化必须更新 OpenAPI Schema 和前端生成类型。

## 失败处理与可观测性

| 故障 | 当前规划行为 |
|---|---|
| 提取模型 timeout/429 | Celery 有限重试；聊天结果不受影响 |
| 模型输出 Schema 无效 | Proposal 不落地，记录安全错误分类 |
| Policy 拒绝 | 保存必要审计或计数，不创建 active memory |
| 重复 Celery 消费 | 幂等键返回已有 Proposal |
| PostgreSQL 写入失败 | 事务回滚，任务按错误类型重试或失败 |
| Store 投影失败 | PostgreSQL 保持权威，标记待修复并后台重建 |
| 用户删除与后台更新并发 | 版本检查失败，后台 Proposal 标记 stale |
| 召回服务不可用 | 降级为无语义记忆，不阻断 Time Steward |

指标至少包括：提取任务数、Schema 失败、Policy allow/reject/confirm、重复 Proposal、用户接受/编辑/拒绝/撤销、投影失败、召回条数、注入 Token 和模型成本。日志不得包含原始敏感对话或完整记忆值。

## 评测与发布门禁

### 离线提取评测

- Memory Candidate Precision / Recall / F1；
- Operation Accuracy；
- Category/Key/Value Accuracy；
- Schema Validity；
- Sensitive-memory rejection rate；
- Prompt Injection rejection rate；
- Conflict resolution accuracy；
- 平均 Token、p50/p95 latency 和 Cost/Task。

### 在线产品指标

- Proposal 接受、编辑后接受、拒绝和撤销比例；
- active memory 陈旧率、冲突率和错误率；
- 记忆命中后建议采纳率；
- Memory on/off 的 Task Success、Tool Accuracy、Constraint Satisfaction；
- 注入前后 Token/Task、TTFT 和 p95 latency。

首个发布门禁不预填数字。唯一硬性安全门槛是测试集中不得出现跨用户泄漏、敏感信息写入或绕过确认的高影响更新。其余阈值必须在 Golden Set 和真实匿名反馈基线建立后确定，当前统一标记为“需要补测”。

## 当前局限与未实现项

当前尚未实现或尚未完成验收：

- 语义记忆专用检索/Embedding 召回；
- 分级直接应用的真实误写率、撤销率和用户中断率基线；
- 聊天消息内嵌撤销控件（当前撤销入口位于 Web 记忆设置页）；
- 内联 Memory Tool 在真实 PostgreSQL Checkpoint、Celery Worker 重启和移动端上的验收；
- 语义记忆污染率、召回准确率及关闭/开启对照评测；
- 真实生产环境下的 Celery、模型调用和故障恢复验收。

已实现但默认关闭的链路包括后台 LLM 受控提取，以及 Agent Search/Remember/Update/Forget
Tool；两条路径都复用 `MemoryPolicy → MemoryProposal → SemanticMemory` PostgreSQL 权威存储，
确认或受控直接应用后的记忆由 `TimeMemoryMiddleware` 有界注入。分级自动接受代码已实现，但
默认 `confirm` 且尚无真实线上评测，不能描述为生产环境已开启。

相关指标均需要补测，不能将对话摘要、行为 Profile 或一次性手工验证描述为语义记忆能力。
