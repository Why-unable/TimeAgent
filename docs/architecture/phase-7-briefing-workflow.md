# Phase 7：Briefing Workflow

## 边界

Phase 7 实现手动简报，不启用天气、新闻、Celery Beat 定时生成或自动投递。PostgreSQL 中的
CalendarEvent 与 Task 是业务事实，BriefingRun 保存的是一次生成时实际使用的数据快照与结果。

## 工作流

```text
initialize BriefingRun
  → Calendar Section ┐
                     ├→ normalize → Briefing Editor → validate/fallback
  → Task Section ────┘                                  ↓
                       persist → ToolMessage(仅 Handoff) → AIMessage → END
```

Calendar 与 Task Section 由 LangGraph 并行执行，各自只能通过 Application Service 读取数据。
Section 完成后由汇合节点顺序持久化结果，避免并发更新同一运行记录。单个 Section 失败产生
`partial` 简报；全部 Section 失败才使 BriefingRun 进入 `failed`。

Editor 使用 `create_agent()` 和 `ToolStrategy(BriefingDraft)`，不配置业务 Tool。模型只接收已
规范化的事实与来源，返回 Pydantic 结构；后端验证来源 ID 后确定性渲染 Markdown。Editor 或
结构校验失败时，从 Section 数据生成确定性降级简报。

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

BriefingRun 保存 Definition 快照、目标日期、时区、状态、结构化结果、Markdown、警告、模型
配置快照和 Prompt 版本。BriefingSectionRun 保存每个 Section 的状态、来源快照、来源引用和
错误码。原始日程和任务仍以各自领域表为权威。
