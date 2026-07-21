# Phase 7：Briefing Workflow

## 边界

Phase 7 建立手动简报、Handoff 和持久化边界；Phase 8 增加天气/新闻，并依据 ADR 0007 将固定
Section 收集升级为短生命周期 Briefing Agent。PostgreSQL 中的 CalendarEvent 与 Task 是业务
事实，BriefingRun 保存一次生成实际使用的调研证据、来源、失败和结果。

## 工作流

```text
initialize BriefingRun
  → BriefingRequest
  → Briefing Agent
      ↔ Calendar/Task/Weather/News read-only tools
  → BriefingAgentReport
  → deterministic coverage/source validation
      ├→ at most one repair invocation
      └→ deterministic fallback
  → persist → ToolMessage(仅 Handoff) → AIMessage → END
```

Briefing Agent 使用 `create_agent()`，并直接传入 `BriefingAgentReport` Schema，由 LangChain
按模型能力自动选择 `ProviderStrategy` 或 `ToolStrategy`。日程、任务 Tool
只能通过 Application Service 读取数据；天气、新闻 Tool 只能通过 Provider Service 读取外部
数据。Agent 内部状态不配置 checkpointer，完成后只把精简调研报告和证据写入 BriefingRun。

后端验证每个请求板块是否实际调用 Tool、日期覆盖是否一致以及来源 ID 是否真实。内容不完整时
最多修复一次；仍失败则从已有证据确定性降级。外部 Tool 使用有限重试，耗尽后作为明确缺口进入
部分简报，不允许无限循环。

## Handoff 与消息

聊天请求由 Time Steward 调用 `transfer_to_briefing`。工具通过 `Command.PARENT` 跳转到父图
`briefing_workflow`，并传递发起调用的 AIMessage 与匹配的 ToolMessage。工作流完成后使用同一
消息 ID 将 ToolMessage 更新为简报结果，再追加最终 AIMessage。Outer Graph 随后到 END，不再
调用 Time Steward 模型。

简报页面的手动运行由 `manual_briefing` Trigger 直接进入工作流，没有模型 Tool Call，因此不
创建 ToolMessage；它写入带 `synthetic=true` 元数据的 HumanMessage 和最终 AIMessage。

最终 Markdown 在校验和持久化后通过 `message.delta` 分块发布。SSE 不是事实来源；断线后可从
AgentEvent 游标和 Conversation/BriefingRun API 恢复。

## 会话分类

Conversation.kind 明确区分：

- `chat`：普通用户聊天；
- `manual_briefing`：简报页面手动生成；
- `scheduled_briefing`：为后续自动简报预留，Phase 7 不创建。

专用页面手动运行会创建 Conversation，并以其 ID 作为 LangGraph thread_id。用户打开该会话后
继续发送消息，会创建新的 `user_message` AgentRun，在同一 thread 上由 Time Steward 处理。

## 可追溯性

BriefingRun 保存 Definition 快照、目标日期、时区、状态、结构化结果、调研报告、Markdown、
警告、模型配置快照和 Prompt 版本。BriefingSectionRun 保存每类调研的状态、来源快照、来源
引用和错误码。原始日程和任务仍以各自领域表为权威。
