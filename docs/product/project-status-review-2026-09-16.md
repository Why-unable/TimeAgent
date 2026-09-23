# Time Agent 项目状态审查（2026-09-16）

## 1. 审查结论

本次审查将 **Phase 10：生产部署与监控** 标记为已完成，并把项目当前阶段更新为
**Phase 11：生产验证、质量闭环与工具集治理**。

这个结论不是把未验证项目写成“已通过”，而是修正原有阶段边界：

- Phase 10 验收工程实现和可发布基线；
- Phase 11 验收真实账号、真实设备、真实流量、长期运行和用户效果证据。

因此，Web/Android 发布、部署配置、观测配置和恢复工具可以支撑 Phase 10 完成；Android
真机矩阵、Google 沙箱、真实通知/告警、隔离恢复、负载安全和真实模型效果仍明确未完成，
已迁移为 Phase 11 的 T092–T099，不得在产品材料中宣称已经验证。

## 2. 审查范围与事实来源

审查以代码和运行产物优先，文档次之，主要核对：

- 根目录 `README.md`、`ROADMAP.md`、`CLAUDE.md`、`PROJECT_SPEC.md`、`FRONTEND_SPEC.md`；
- `docs/` 下的产品、架构、运维、Android 和工具集文档；
- 实际 `TIME_STEWARD_TOOLS` 注册表；
- Android Gradle 版本和 `releases/` 发布产物；
- 当前工作树及既有测试、部署验收记录。

本次为文档与状态审查，没有重新执行全部后端、前端、E2E、真实 Provider 或真机测试。
历史测试数字仅作为既有证据保留，不被解释为 2026-09-16 的重新验证结果。

## 3. 当前已完成能力

| 领域 | 已完成事实 | 审查结论 |
|---|---|---|
| 核心事务 | 日程、任务、提醒、Today、冲突检测、空闲时间和确定性通知 | 已完成 |
| Agent | `create_agent()`、LangGraph 持久化、SSE、审计、HITL、Briefing Handoff | 已完成 |
| 规划闭环 | 日/周计划草案、比较、校验、应用、局部重排、撤销和执行信号 | 已完成工程实现 |
| 外部信息 | 天气、新闻、ICS 与 Google Calendar 只读同步实现 | 已完成工程实现；部分真实环境待 Phase 11 |
| 账户与客户端 | Session/Token、注册登录、游客空间、Web PWA、Capacitor Android | 已完成工程实现 |
| 生产基线 | Compose、Uvicorn、Nginx/Cloudflare、TLS、健康检查、结构化日志 | 已完成并已有部署 |
| 可观测性 | Prometheus、Grafana、Alertmanager、Loki、Alloy、业务 SLI 与 LLM 审计 | 配置与代码完成；真实送达待 Phase 11 |
| 恢复能力 | PostgreSQL 备份/恢复脚本和运维说明 | 工具完成；隔离恢复演练待 Phase 11 |
| Android 发布 | `1.1.8 / versionCode 12`，APK 已签名和发布 | 发布完成；真机矩阵待 Phase 11 |
| 工具集 | 44 个名称唯一的注册 Tool，20 个只读/控制流入口、24 个写入入口 | 现状已核实；治理待 Phase 11 |

Android `1.1.8` 当前仓库产物：

```text
文件：releases/timeagent-1.1.8.apk
大小：4,175,871 bytes
SHA-256：458bb5820e7c1dd8e02120f56c5bf99c758e8c087425184c290dc36cb72e2980
签名证书 SHA-256：e7fb9f63eff74b44c3ec32dafdcb2c726ff2d031c5c7614f70dda486916a783e
```

## 4. 文档与代码的主要差异

### 4.1 阶段口径漂移

审查前，`README.md`、`ROADMAP.md` 和 `CLAUDE.md` 仍把项目写成 Phase 10 进行中，且把工程实现与
外部运行证据放在同一个完成条件中。此次更新将 Phase 10 定义为生产工程基线完成，并把
外部实证迁入 Phase 11。

### 4.2 Android 版本滞后

审查前，部分产品和 Android 文档仍把 `1.1.7 / versionCode 11` 作为当前版本，而 Gradle 和
当前发布产物已经是 `1.1.8 / versionCode 12`。当前版本统一引用 1.1.8；1.1.7 只保留为
历史发布记录。

### 4.3 Tool 数量和名称滞后

审查前，项目经历类文档仍记录 40 个注册 Tool。实际注册表为 44 个：20 个只读/控制流入口、24 个
写入入口，名称全部唯一。README 还使用了未注册的 `create_event`/`cancel_event` 描述当前
审批能力；当前 Event 写入口是 `mutate_events` 和 `create_recurring_event`。

详细核实和优化建议见 [Time Steward 工具集核实与优化讨论](../toolset-optimization/README.md)。

### 4.4 规范阶段编号不是当前交付状态

`PROJECT_SPEC.md` 的“阶段 0–10”是早期产品能力分解，其中“阶段 10”指高级规划；它与
`ROADMAP.md` 的交付 Phase 10“生产部署与监控”不是同一套编号。规范可以保留历史设计，
但必须显式声明当前项目状态只以 `ROADMAP.md` 为准。

### 4.5 历史测试数字容易被误读

产品材料中的 `474 passed`、`107 passed`、`27 passed` 等是特定日期和工作树的历史结果，
不能自动代表当前未提交工作树。今后测试记录必须同时包含提交、日期、环境与命令。

## 5. Phase 10 完成边界

Phase 10 以以下事实作为完成条件：

1. 生产身份、部署、代理、TLS、健康检查和安全配置已经落地；
2. 日志、指标、Dashboard、告警配置和 LLM 审计链路已经具备；
3. 备份恢复脚本、显式确认和运维步骤已经具备；
4. Web 已部署，Android 可生成兼容签名的版本化产物并通过自托管清单发布；
5. 长期记忆、写串行化、双坐标天气和游客隔离均已进入代码与测试体系。

以下项目不计入 Phase 10 的工程完成条件，也没有被宣称已验证：

- 第三方账号的长期、限流和撤权行为；
- 真实邮件、Web Push 和 Alertmanager 端到端送达；
- 生产规模负载、攻击面和长时间稳定性；
- Android 多型号真机和系统升级行为；
- 恢复时间/恢复点目标和真实灾难恢复能力；
- 真实用户对计划质量、估时和提醒价值的长期反馈。

## 6. Phase 11 交付清单

Phase 11 按 `ROADMAP.md` 的 T092–T099 执行，优先顺序如下：

1. Tool Manifest、风险策略孤儿名称、副作用分类和批量排程原子性；
2. Google Calendar、SMTP/Web Push、天气与告警的专用测试环境证据；
3. Android 1.1.8 真机矩阵；
4. 隔离恢复、应用回滚、API/SSE/Celery/Agent 分层负载和安全基线；
5. 真实模型轨迹、成本、延迟和发布门禁；
6. 计划采纳、用户修改、撤销、完成率和估时偏差等产品效果指标。

每项验收记录必须包含：代码提交、版本、执行日期、环境、可重复命令、脱敏结果、已知限制
和明确结论。没有证据时统一写 `NOT VERIFIED`，不能使用“基本完成”“应该可用”等模糊措辞。

## 7. 明确不纳入 Phase 11

Microsoft Calendar、Webhook、外部日历写回、应用商店发布、Telegram/SMS、Kubernetes、
微服务、向量数据库和复杂 RBAC 均未因本次阶段调整而获得开发授权；需要时应单独定义范围、
风险与 ADR。
