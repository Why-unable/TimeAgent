# Time Agent 开发规则

本文件中的规则适用于本仓库中的所有 Coding Agent 和人工贡献者。

1. PostgreSQL 是业务事实的唯一权威来源，Memory、聊天记录和缓存不得替代业务数据库。
2. Agent Tool 不得直接访问 Django ORM，调用链必须是 Tool → Application Service → Domain/Repository → ORM。
3. 所有改变业务事实的写操作必须经过 Application Service，并具备审计和幂等设计。
4. 数据库时间统一保存为 UTC；用户输入和展示时间必须结合明确的 IANA 时区解析。
5. 相对时间必须注入明确的当前时间，不得依赖模型或测试机器的隐式系统时间。
6. Time Steward Agent 必须使用 LangChain `create_agent()` 创建。
7. 外层 LangGraph 只负责触发路由、Handoff、中断恢复和确定性工作流编排，不重复拆解 Agent 内部循环。
8. 定时提醒必须由确定性的 Celery Dispatcher 执行，不得经过 LLM。
9. 定时简报必须直接进入 Briefing Workflow，不先调用 Time Steward Agent。
10. 高风险操作必须创建 ActionProposal，并通过 HITL 审批后才能执行。
11. Agent 必须配置模型调用、工具调用和重试上限，并提供安全退出路径。
12. 长期 Memory 写入必须经过 Memory Policy，不得保存无关对话或敏感信息。
13. 天气、新闻、日历、邮件、通知和模型等外部服务必须通过可替换 Provider 接口接入。
14. 前端不得复制后端业务规则；冲突、权限、状态机、幂等和风险判断以后端为准。
15. 页面和组件不得散落原始 `fetch()`；统一通过 `frontend/src/api/client.ts` 和 feature API。
16. 新增或修改 API 后必须重新生成 OpenAPI Schema 和前端类型，并提交契约变更。
17. 所有新功能必须包含与风险相称的单元、组件或集成测试。
18. 不得记录 API Key、Token、认证 Cookie、用户敏感信息或模型私有推理。
19. 未明确要求时不得修改任务范围之外的文件，也不得静默删除已有实现。
20. 当前阶段不得提前实现大规模多 Agent、微服务、向量数据库或复杂 RBAC。
21. 不得为了“架构完整”创建没有实际用途的空抽象层、伪接口或伪 Agent。
22. 后端环境和依赖统一使用 `uv`，必须维护 `pyproject.toml` 与 `uv.lock`，禁止提交临时 `pip freeze` 清单。
23. 前端依赖统一使用 npm 和 `package-lock.json`，敏感配置不得进入 `VITE_*` 变量。
24. 每次修改后至少运行相关格式/静态检查、测试、Django system check 和迁移检查。
25. 新增 Agent、改变持久化边界或部署拓扑等重要决策必须记录 ADR。

