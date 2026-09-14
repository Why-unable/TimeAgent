# Prompt Cache 上下文布局设计

## 文档状态

- 状态：设计建议，尚未改变生产运行链路
- 适用范围：Time Steward Agent 的模型请求上下文
- 目标：在不削弱时间锚点、权限和长期记忆约束的前提下，保持尽可能稳定的 Prompt 前缀

## 当前实现

当前 Agent 通过 `runtime_system_prompt` 生成一条动态 `SystemMessage`（`backend/apps/agents/middleware.py`）。该消息同时包含：

- `BASE_SYSTEM_PROMPT` 中的稳定 Agent 规则；
- 本次运行的时间锚点、本地时间、UTC 时间、时区和语言；
- 读写模式；
- 用户称呼；
- 用户规划偏好。

`TimeMemoryMiddleware`（`backend/apps/time_memory/middleware.py`）还会把按用户、请求意图和当前时间生成的长期记忆提示追加到这条系统消息中。

历史消息由 `TemporalContextMiddleware`（`backend/apps/agents/middleware.py`）在模型调用前复制并规范化。历史对话仍是 `HumanMessage`、`AIMessage` 和 `ToolMessage`，不是系统指令；Checkpoint 中保存的原始消息不被改写。

当前没有显式的 Provider Prompt Cache 配置、缓存控制字段、缓存命中率或缓存成本指标。因此，当前实现只能称为“上下文规模受控”，不能称为“已完成 Prompt Cache 优化”。

## 推荐消息布局

```text
SystemMessage 1：稳定前缀
  Agent 身份、工具规则、安全边界、时间解释规则、输出约束

历史消息
  历史 HumanMessage / AIMessage / ToolMessage

SystemMessage 2：本次运行动态上下文
  当前时间锚点、时区、语言、运行模式、用户偏好、相关长期记忆

HumanMessage：当前请求
```

动态系统消息必须由服务端从 `RuntimeContext` 和受控的 Memory Profile 生成，不能由用户输入覆盖。当前请求仍必须是最后一条 `HumanMessage`，工具返回仍使用 `ToolMessage`。

## 前置稳定 SystemMessage

应放入第一条系统消息的内容来自 `backend/apps/agents/prompts/time_steward.md`，包括：

- Agent 身份和职责；
- 不可信外部数据与 Prompt Injection 防护；
- 工具选择、参数和权限边界；
- 相对时间解析和写操作约束；
- 审批、失败降级和保密要求；
- 简报、空闲时间、容量预测、重规划等业务规则。

这些内容跨用户、跨请求基本稳定，适合作为缓存前缀。若业务规则变更，应视为稳定前缀版本变化，而不是每轮动态数据变化。

## 后置动态 SystemMessage

以下内容应从当前动态系统提示中拆出，并放在历史消息之后、当前用户请求之前：

- 本次运行固定时间锚点及其用户时区表示；
- 用户时区、语言区域和读写模式；
- 用户称呼等用户资料；
- 当前规划偏好和审批偏好；
- 本轮召回的长期时间记忆；
- 只对本次运行有效的其他服务端上下文。

`request_id`、数据库主键等纯追踪字段不需要进入模型上下文，除非某个工具协议明确要求它们。

长期记忆属于动态上下文，即使内容跨多轮相对稳定，也不能并入全局稳定前缀，因为它按用户、意图、Token Budget 和时间变化。

## 不应调整的边界

- 历史消息不能改成 `SystemMessage`，否则模型可能把历史回答当成当前规则；
- 用户消息不能拼接服务端时间，避免混淆用户事实与系统事实；
- 工具结果不能提升为系统指令，必须保留 `ToolMessage` 和不可信数据边界；
- 当前时间不能由模型自行推断，仍以 `RuntimeContext.current_datetime` 为唯一锚点；
- Prompt Cache 不能替代 PostgreSQL、Checkpoint 或 Memory 的权威持久化。

## Provider 兼容性要求

项目当前配置使用 OpenAI-compatible Provider 和 Anthropic Provider（`backend/config/agent.yaml`）。多条 `SystemMessage` 在 LangChain 层面是合法的，但不同网关可能合并、重排或转换系统消息。因此实施时必须分别验证：

1. DeepSeek/OpenAI-compatible 请求中系统消息顺序是否保持；
2. Claude 请求中动态系统消息是否仍位于当前用户请求之前；
3. 工具调用时动态上下文是否在每次模型调用中保持；
4. 摘要中间件触发后，消息布局是否仍符合上述边界。

如果某个 Provider 不支持后置系统消息，应在 Provider 适配层将“稳定前缀 + 历史 + 动态上下文”规范化为等价的单条 system 内容，而不是让前端或业务代码分别处理。

## 实施顺序

1. 将 `BASE_SYSTEM_PROMPT` 与稳定时间规则固定为第一条系统消息；
2. 将 `runtime_system_prompt` 中的运行时字段改为后置动态系统消息；
3. 将 `TimeMemoryMiddleware` 的记忆提示放入同一动态区域，避免污染稳定前缀；
4. 保持 `TemporalContextMiddleware` 的历史时间隔离和旧时钟工具调用清理逻辑；
5. 对 DeepSeek 和 Claude 增加消息顺序集成测试；
6. 增加输入 Token、缓存命中率、缓存节省 Token、TTFT、p95 延迟和成本/任务指标。

## 验收方法

使用固定用户、固定多轮对话和固定工具结果，分别运行：

- 当前布局；
- 稳定前缀与动态后置上下文布局；
- 开启和关闭 Provider Prompt Cache（若 Provider 支持）。

至少比较：

- 输入 Token 数；
- 缓存命中率和缓存 Token；
- TTFT、p50、p95 延迟；
- 模型调用成本；
- 相对时间解析正确率；
- 工具选择和参数正确率；
- 长期记忆注入后的任务成功率。

当前上述实验数据均为“需要补测”，不能在简历或项目文档中宣称已有缓存收益。

## 当前局限

- 尚未实现多条系统消息的运行时拆分；
- 尚未确认所有实际模型网关对后置系统消息的处理方式；
- 尚无 Prompt Cache 命中和节省成本的观测指标；
- 摘要是按消息数量阈值周期性生成，尚无摘要版本化和复用；
- Checkpoint 历史持久化与 Provider Prompt Cache 仍是两个独立层次，不能相互替代。

