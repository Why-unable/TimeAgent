# Agent 统一配置

Time Agent 使用 `backend/config/agent.example.yaml` 统一管理模型、Outer Graph 限制和 Agent
Middleware 参数。该设计参考了 `other_files/config.example.yaml` 的集中式配置思想，但只保留
当前项目实际需要的字段，并禁止通过字符串动态导入任意 Python 类。

## 配置边界

YAML 保存可审查、可版本化的非敏感配置：

- 默认模型、按顺序尝试的回退模型别名和模型 ID；
- 模型 provider、base URL、超时、temperature、输出和 reasoning 参数；
- LangGraph recursion limit 与并发限制；
- Model/Tool 调用上限和重试次数；
- Summarization 开关、触发消息数和保留消息数。

环境变量保存部署相关或敏感配置：

- API Key；
- Django/PostgreSQL/Redis 密钥和连接信息；
- `TIME_AGENT_CONFIG_PATH` 配置文件位置。

YAML 字段可用完整的 `$NAME` 或 `${NAME}` 引用环境变量。加载器只替换完整字段值，不进行
任意 shell expansion；SecretStr 的日志/repr 不显示密钥。

## 使用方式

默认直接加载：

```text
backend/config/agent.example.yaml
```

创建本地配置：

```bash
cp backend/config/agent.example.yaml backend/config/agent.yaml
```

然后在 `.env` 中设置：

```text
TIME_AGENT_CONFIG_PATH=config/agent.yaml
AGENT_API_KEY=...
```

相对路径以 Django `BASE_DIR`（即 `backend/`，容器内为 `/app`）解析。`agent.yaml` 已加入
`.gitignore`，Docker 构建时仍会随 backend build context 复制到 `/app/config/agent.yaml`。

## 校验和加载

`apps.agents.configuration` 使用 `yaml.safe_load()` 和禁止未知字段的 Pydantic Schema。配置版本、
模型别名、正整数限制、temperature、摘要保留关系等在使用前统一校验。配置通过进程级缓存
读取，因此修改后必须重启 Django、Celery Worker 和其他 Agent 进程。

`python manage.py check` 会通过 `agents.E001` 报告配置错误，也可单独运行
`uv run python manage.py check_agent_config` 查看已选择的配置路径、模型别名和 provider；命令
不会输出 API Key。

当前通过 LangChain `init_chat_model()` 显式注册两个 provider adapter：

- `openai_compatible` 使用 LangChain `openai` provider，可连接 DeepSeek 等 OpenAI 协议服务；
- `anthropic` 使用 LangChain `anthropic` provider，可连接 Claude 原生 Messages API。

`agent.fallback_models` 是有序模型别名列表。主模型在 `ModelRetryMiddleware` 耗尽重试后，
LangChain 官方 `ModelFallbackMiddleware` 按该列表切换模型。默认示例保持空列表，避免未配置
备用密钥时阻止 Agent 初始化；部署环境可按可用 Provider 显式开启。

Anthropic SDK 会在 `base_url` 后追加 `/v1/messages`，因此 Anthropic-compatible 中转站应填写
API root，不要带尾部 `/v1`。如果中转站在流式结尾返回非标准 usage metadata，可配置
`stream_usage: false`，这只关闭 usage chunk 解析，不关闭 token 流式输出。

未来增加 Gemini 或 Ollama 时，应在代码中增加显式 provider adapter 和对应依赖，不能接受
YAML 中的任意 `module:class` 导入，以免配置文件成为代码执行入口。
