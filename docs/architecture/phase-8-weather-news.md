# Phase 8：天气与新闻 Provider

## 数据流

```text
UserPreference.weather_location ──> WeatherDataService ──> WeatherProvider
                                                        └─> Weather Section

UserPreference.news_topics ──> 主题归一/别名展开 ──> 可信 Feed 路由
                                               └─> RSS/Atom 拉取
                                                   └─> 时间过滤、相关性排序
                                                       └─> 去重、PostgreSQL 留存
                                                           └─> News Section

Calendar + Task + Weather + News Sections
  └─> Briefing Editor（只读取规范化事实）
      └─> 来源校验 ──> Markdown/AIMessage
```

## Feed 与用户主题

Feed 由运维方在 `backend/config/providers.yaml` 中维护，用户只保存主题，不保存任意 URL。`topic_aliases` 将 `AI`、`人工智能`、`LLM` 等输入归一为 `artificial intelligence`。Feed 的 `topics` 声明其覆盖范围，只有相交的 Feed 才会被请求。条目按 Feed 优先级、标题/摘要/分类关键词命中数和发布时间排序。

默认目录同时覆盖国际来源与国内中文来源。国内来源包括中国新闻网即时/财经、InfoQ 中文、量子位、开源中国、Solidot、爱范儿和 36氪。抓取使用 `max_concurrent_feeds` 控制的受限线程池；完成结果按配置顺序消费，因此网络完成顺序不会改变 warning 与等分条目的顺序。

未被目录覆盖的主题会写入 Section warning。系统不会让模型自行选择来源，也不会把未知主题退化为不受控网页抓取。新增 Feed 时必须确认来源归属、HTTPS、RSS/Atom 格式、使用条款和稳定性，并通过 `check_external_providers` 验证。

## 边界与降级

- Open-Meteo 负责地点解析和未来天气；用户时区与本次工作流的明确当前时间由调用方注入。
- RSS Provider 支持 ETag/Last-Modified 条件请求、响应大小上限和逐 Feed 超时隔离。
- `ExternalNewsItem` 保存规范化新闻事实与稳定指纹；BriefingRun 保存本次使用的来源快照。
- 单个 Feed 失败产生 warning；所有已选择 Feed 失败只使 News Section 失败；其他 Section 仍可生成简报。
- Briefing Editor 没有外部读取或业务写入 Tool，只能基于 Section 数据编辑，最终来源 ID 由后端校验。

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

Briefing Editor 延续 LangChain v1 官方的 [`create_agent` 结构化输出](https://docs.langchain.com/oss/python/langchain/structured-output)方式，使用 Pydantic `BriefingDraft` 与 `ToolStrategy`。Provider 收集仍位于外层确定性工作流中，不作为 Editor 的联网 Tool。
