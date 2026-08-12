# 生产监控、告警与评测

## 1. 当前覆盖

监控栈使用 Prometheus、Grafana、Alertmanager、Loki 和 Grafana Alloy。基础设施 Exporter 覆盖 PostgreSQL、Redis、Celery；Django `/metrics` 额外暴露低基数业务 SLI：Agent/Tool/Briefing/Notification 24 小时结果、Agent p50/p95 时延、卡住的运行、ActionProposal 状态、逆地理编码结果与延迟，以及 LLM 调用和 Token 使用情况。

每次 LLM 调用都会写入不含提示词和回答正文的 `LLMCallAudit`：输入、输出、总 Token，记忆 Prompt Token、记忆占输入比例、模型、组件、耗时、状态和关联请求编号。Prometheus 只输出低基数的 24 小时聚合和 p50/p95；单次调用在 Django Admin 或 Loki 中按 `request_id` 查询。

禁止把 `user_id`、`request_id`、会话 ID、API Key、请求正文或模型私有推理作为 Prometheus label。单次故障通过日志中的 `request_id` 关联，而不是制造高基数时序。

## 2. 启动

先在 `.env` 设置一个强 Grafana 密码：

```env
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=replace-with-a-long-random-password
GRAFANA_PORT=3000
PROMETHEUS_PORT=9090
ALERTMANAGER_PORT=9093
```

然后启动同一个 Time Agent Compose project：

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.observability.yml \
  up -d
```

所有 UI 默认只监听 `127.0.0.1`。通过 SSH 转发访问 Grafana：

```bash
ssh -L 3000:127.0.0.1:3000 user@server
```

不要直接经 Cloudflare 公开 Grafana、Prometheus、Alertmanager、Loki 或 `/metrics`。

## 3. 告警路由

Alertmanager 启动前由一次性配置容器复用 Django/Celery 的 `EMAIL_*` SMTP 配置生成只保存在 Docker volume 中的配置，并发送到 `ALERTMANAGER_EMAIL_TO`；未设置时发送到 `EMAIL_USERNAME`。`EMAIL_USE_SSL=true` 使用 465 等端口的隐式 TLS，`EMAIL_USE_TLS=true` 使用 587 等端口的 STARTTLS，两者不得混用。SMTP 密码不会写入仓库。上线后必须用临时告警验证“触发—送达—恢复”全链路。

基线告警包括：Django/PostgreSQL/Redis/Celery 不可用、HTTP 5xx 比例和 p95 时延过高、Celery 任务失败、Agent 失败率、卡住的 AgentRun、通知发送失败。

## 4. 日志排障

Grafana 的“Time Agent / 生产概览”包含 Loki 日志面板、24 小时 Agent 错误数和提示词注入信号数。用户报告错误时，以 App 显示的请求编号查询日志。日志使用可解析 JSON，只记录错误类型和运行标识，不保存异常正文、用户聊天正文或密钥。

## 5. 离线发布评测

固定数据集位于 `backend/tests/fixtures/time_steward_eval.json`。正式发布必须执行完整门禁：

```bash
make release-gate EVALUATION_MODEL=deepseek
```

该目标依次执行后端和前端测试、lint、mypy、构建、迁移漂移检查，然后构建当前后端镜像，并在 Compose 网络内使用真实目标模型执行：

```bash
make release-eval EVALUATION_MODEL=deepseek
```

容器内评测与生产使用相同的 PostgreSQL、Redis、依赖和服务命名；评测事务始终回滚。命令仅挂载本次报告文件，退出时将其权限收紧为 `0600`，并保存到 `backend/evaluation_reports/`。

报告记录 schema、Git commit（通过 `GIT_COMMIT_SHA` 注入）、数据集 SHA-256、系统提示词 SHA-256、模型、每例工具轨迹、禁止工具、泄漏模式、时延和汇总通过率。报告不保存完整模型回答，以降低敏感信息扩散风险。

发布门禁为：所有用例通过、禁止工具调用数为 0、提示词/凭据/Memory 内部结构泄漏命中数为 0。模型、提示词、工具 Schema 或 Memory 注入策略变化后必须重跑并与上一份报告比较。禁止在真实模型评测失败时继续执行生产发布。

## 6. 在线质量闭环

生产监控负责可用性、时延、错误和确定性业务结果；离线数据集负责正确性回归。真实失败只在完成脱敏和人工确认后加入版本化数据集。若启用 LangSmith，应先定义采样率、数据驻留、保留期、访问权限和删除流程，再配置在线 evaluator；默认部署不向第三方发送聊天内容。
