# Phase 8：天气与新闻 Provider

## 数据流

```text
BriefingRequest ──> Briefing Agent ──> research_weather ──> WeatherDataService
                                                        └─> WeatherProvider

BriefingRequest.news_topics ──> research_news ──> 主题归一/别名展开 ──> 可信 Feed 路由
                                               └─> RSS/Atom 拉取
                                                   └─> 时间过滤、相关性排序
                                                       └─> 去重、PostgreSQL 留存
                                                           └─> 调研证据

Calendar + Task + Weather + News 只读 Tool
  └─> Briefing Agent（短生命周期、无独立对话持久化）
      └─> BriefingAgentReport ──> 确定性完整性/来源校验
          ├─> 最多一次修复
          └─> Markdown/AIMessage + 调研报告
```

## Feed 与用户主题

Feed 由运维方在 `backend/config/providers.yaml` 中维护，用户只保存主题，不保存任意 URL。`topic_aliases` 将 `AI`、`人工智能`、`LLM` 等输入归一为 `artificial intelligence`。Feed 的 `topics` 声明优先路由范围；主题没有目录映射时，它会被视为关键词，在整个可信 Feed 目录中检索，而不是配置错误。回退 Feed 只保留标题、摘要或分类实际命中关键词的条目。条目按 Feed 优先级、关键词命中数和发布时间排序。

默认目录同时覆盖国际来源与国内中文来源。国内来源包括中国新闻网即时/财经、InfoQ 中文、量子位、开源中国、Solidot、爱范儿和 36氪。抓取使用 `max_concurrent_feeds` 控制的受限线程池；完成结果按配置顺序消费，因此网络完成顺序不会改变 warning 与等分条目的顺序。

未被目录标签覆盖的主题会写入调研 warning，但仍会进行可信目录关键词检索。系统不会让模型提供任意 Feed URL，也不会把未知主题退化为不受控网页抓取。新增 Feed 时必须确认来源归属、HTTPS、RSS/Atom 格式、使用条款和稳定性，并通过 `check_external_providers` 验证。

## 边界与降级

- Open-Meteo 负责地点解析和最长 16 天的未来天气；日期范围、用户时区与明确当前时间由 BriefingRequest/RuntimeContext 注入。
- RSS Provider 支持 ETag/Last-Modified 条件请求、响应大小上限和逐 Feed 超时隔离。
- `ExternalNewsItem` 保存规范化新闻事实与稳定指纹；BriefingRun 保存本次使用的来源快照。
- 单个 Feed 失败产生 warning；全部 Feed 失败会由 Tool Middleware 有限重试，耗尽后作为调研失败交还 Agent，其他部分仍可生成。
- Briefing Agent 的日程和任务 Tool 只读；天气和新闻 Tool 只能读取 Provider。最终来源 ID 与请求覆盖范围由后端确定性校验。

## 配置示例

```yaml
news:
  topic_aliases:
    artificial intelligence: [ai, 人工智能, llm]
  feeds:
    - name: OpenAI News
      url: https://openai.com/news/rss.xml
      publisher: OpenAI
      topics: [artificial intelligence, openai]
      priority: 100
```

敏感密钥仍应放在环境变量中；当前 Open-Meteo 和公开 Feed 不需要密钥。

Briefing Agent 使用 LangChain v1 官方 [`create_agent`](https://docs.langchain.com/oss/python/langchain/agents)、自动选择的[结构化输出策略](https://docs.langchain.com/oss/python/langchain/structured-output)和[`ToolRetryMiddleware`](https://docs.langchain.com/oss/python/langchain/middleware/built-in)。外层 LangGraph 仅负责触发、Handoff、持久化、确定性校验和一次有限修复，不重复实现 Agent 内部 Tool 循环。
