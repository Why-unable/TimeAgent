# ADR 0005：确定性 Briefing Workflow 与会话分类

- 状态：Accepted
- 日期：2026-07-19

## 背景

简报需要同时满足并行采集、部分失败、模型编辑、来源追溯和聊天后续交互。如果将整个过程交给
自由 Agent，数据范围、失败语义和持久化时机难以保证；如果只保存 Markdown，又无法解释模型
实际看到了哪些事实。手动和未来自动简报若混入普通聊天列表，也会造成产品语义混乱。

## 决策

1. Briefing Workflow 使用独立 BriefingState；Outer AppState 只接收最终 messages 与结果引用。
2. Section 通过 Registry 注册并并行读取，调用链保持 Section → Application Service → ORM。
3. Editor 使用无业务 Tool 的 `create_agent()` 和结构化输出，最终 Markdown 由确定性 Renderer 生成。
4. BriefingDefinition、BriefingRun、BriefingSectionRun 保存配置、运行、来源和部分失败事实。
5. 聊天 Handoff 使用官方 `Command.PARENT`，保留匹配的 AIMessage tool call 与 ToolMessage。
6. 最终简报总是 AIMessage；运行在 END 结束，下一条用户消息在同一 thread 开启新 Run。
7. 只有真实模型 Tool Call 路径创建 ToolMessage。直接手动或未来定时 Trigger 不伪造工具调用。
8. Conversation.kind 区分普通聊天、手动简报与自动简报，前端分类展示。
9. Phase 7 仅启用手动日历/任务简报；天气、新闻和定时自动生成留在后续阶段。

## 结果

工作流具有明确的降级和审计边界，新 Section 可通过 Registry 加入。简报可以作为会话上下文继续
追问，同时不会要求 Time Steward 在简报完成后再次生成回复。代价是新增三张领域表，并需要在
Conversation/AgentRun 契约中显式记录会话和触发类型。
