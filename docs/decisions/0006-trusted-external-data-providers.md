# ADR 0006：可信外部数据 Provider 与主题驱动 Feed 路由

- 状态：Accepted；简报执行方式由 ADR 0007 修订
- 日期：2026-07-19

## 背景

天气和新闻来自不稳定的外部系统，但简报必须保留来源、限制抓取边界，并在部分失败时继续生成。若允许用户或模型直接提交任意 Feed/URL，会引入 SSRF、来源质量和不可复现问题。ADR 0007 允许 Briefing Agent 调用受控 Provider Tool，但不改变可信目录边界。

## 决策

1. 外部服务通过 `WeatherProvider` 和 `NewsProvider` 协议接入，Briefing Tool 只依赖 Provider/Application Service。
2. Feed 目录由服务端 YAML 管理，只接受 HTTPS；用户偏好只保存天气地点和新闻主题。
3. 新闻主题先进行别名归一，再路由到声明覆盖该主题的 Feed；未知主题在整个可信目录中做关键词回退检索并明确警告，不自动进行网页搜索。
4. RSS/Atom 响应按明确时间窗口过滤，保留发布方、URL 和发布时间，并以 URL、稳定指纹和近似标题去重。
5. 规范化新闻写入 PostgreSQL；BriefingRun/SectionRun 保存本次使用的快照与来源。
6. Provider 使用有限超时、响应大小上限和条件请求。单 Feed 失败不终止其他调研 Tool。
7. Briefing Agent 只能通过受控 Tool 访问 Provider，不能提交任意 URL；输出中的每个天气和新闻项目都必须引用已知来源 ID。

## 结果

用户通过少量主题即可影响可信来源的选择和排序，运维方可以审计或替换 Provider。目录标签未覆盖的主题可能通过可信目录关键词检索得到结果，但不会扩展到任意网页；新增来源仍需要显式配置和验证。
