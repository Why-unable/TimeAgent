# 前端架构规范

## 1. 前端定位

Time Agent 前端不是单纯的聊天页面，而是用户管理时间、查看计划、审批 Agent 操作和阅读简报的统一工作台。

前端需要同时支持：

* 与 Time Steward Agent 对话；
* 实时展示 Agent 执行过程；
* 查看和管理日程、任务、提醒；
* 展示 Agent 生成的时间安排草案；
* 审批、修改或拒绝高风险操作；
* 查看和配置每日简报；
* 接收天气、新闻和事务提醒；
* 管理用户时间偏好和外部集成；
* 在桌面端和移动端浏览器中使用。

前端的核心职责是：

```text
展示业务事实
    +
承载 Agent 交互
    +
收集用户审批
    +
提供事务管理界面
    +
展示执行状态
```

前端不能承担后端业务规则。

---

# 2. 前端设计原则

## 2.1 聊天不是唯一入口

用户既可以通过自然语言操作，也可以通过传统界面直接管理数据。

系统应同时提供：

```text
聊天入口
├── 创建提醒
├── 查询安排
├── 规划时间
└── 生成简报

结构化入口
├── 日历
├── 任务列表
├── 提醒列表
├── 简报配置
└── 用户设置
```

用户不应被迫通过聊天才能查看或修改自己的事务。

---

## 2.2 前端不实现关键业务规则

前端可以做输入层面的基础校验，例如：

* 必填字段；
* 日期格式；
* 结束时间晚于开始时间；
* 字符长度；
* 表单类型检查。

但以下规则必须由后端最终判断：

* 日程冲突；
* 用户权限；
* 重复事件修改范围；
* 提醒是否重复；
* 任务状态是否允许转换；
* ActionProposal 是否仍然有效；
* 幂等；
* 外部日历同步冲突。

前端校验只用于改善体验，不能替代后端校验。

---

## 2.3 Agent 状态必须可见

当 Agent 正在执行任务时，前端应明确展示：

* 当前是否正在运行；
* 当前正在查询什么；
* 是否正在调用工具；
* 是否正在生成计划；
* 是否需要用户审批；
* 是否已经完成；
* 是否部分失败；
* 是否因为调用限制而提前结束。

禁止只显示一个长时间旋转的加载图标。

推荐展示：

```text
正在读取本周日程……
正在搜索两个一小时的空闲时间……
发现 3 个候选时间……
正在检查时间冲突……
已生成安排草案。
```

这些信息来自后端 SSE 事件，而不是前端自行猜测。

---

## 2.4 高风险操作必须显式审批

当 Agent 准备执行高风险操作时，前端必须展示结构化审批卡片。

用户可以：

* 批准；
* 编辑后批准；
* 拒绝。

不能只通过普通聊天文字询问：

```text
你确认吗？
```

应该显示具体操作内容：

```text
创建日程

标题：健身
时间：2026-07-17 19:00–20:00
时区：Asia/Singapore
提醒：提前 30 分钟
冲突：无
影响范围：仅此事件
```

---

## 2.5 时间展示必须统一

前端所有时间展示遵循：

* 后端返回 ISO 8601；
* 前端根据用户 IANA 时区显示；
* 页面明确显示当前使用的时区；
* 编辑表单保留事件原始时区；
* 不直接使用浏览器本地时区覆盖用户配置；
* 跨天、全天事件和重复事件需要特殊展示。

例如：

```text
7 月 17 日 周五 19:00–20:00
Asia/Singapore
```

---

# 3. 推荐技术栈

第一版推荐使用独立 SPA：

| 模块          | 技术选择                           |
| ----------- | ------------------------------ |
| 前端框架        | React + TypeScript             |
| 构建工具        | Vite                           |
| 路由          | React Router                   |
| 服务端状态       | TanStack Query                 |
| 客户端轻量状态     | Zustand                        |
| 表单          | React Hook Form                |
| Schema 校验   | Zod                            |
| UI 组件       | shadcn/ui 或等价可维护组件库            |
| 样式          | Tailwind CSS                   |
| 日期处理        | date-fns + date-fns-tz 或 Luxon |
| 日历组件        | FullCalendar                   |
| Markdown 渲染 | react-markdown                 |
| 图标          | Lucide                         |
| 测试          | Vitest + React Testing Library |
| 端到端测试       | Playwright                     |
| API 类型生成    | OpenAPI TypeScript Generator   |
| 部署          | Docker + Nginx                 |

第一版不建议为了 SSR 引入额外复杂度。

如果后续需要：

* 公共简报分享页；
* 搜索引擎索引；
* 服务端渲染；
* 多租户门户；

再考虑迁移到 Next.js。

---

# 4. 前端总体架构

```text
┌───────────────────────────────────────────┐
│               Browser / PWA               │
└─────────────────────┬─────────────────────┘
                      │
                      ▼
┌───────────────────────────────────────────┐
│                 React App                 │
│                                           │
│ Router                                    │
│ Layout                                    │
│ Pages                                     │
│ Feature Modules                           │
└───────────────┬───────────────────────────┘
                │
       ┌────────┴────────┐
       │                 │
       ▼                 ▼
┌───────────────┐  ┌────────────────────────┐
│ TanStack Query│  │ Zustand                │
│               │  │                        │
│ API 数据       │  │ UI 状态               │
│ 缓存与刷新     │  │ 当前会话              │
│ Mutation      │  │ 面板开关               │
└───────┬───────┘  └────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────┐
│ API Client                                │
│                                           │
│ REST                                      │
│ SSE                                       │
│ Authentication                            │
│ Error Mapping                             │
└─────────────────────┬─────────────────────┘
                      │
                      ▼
┌───────────────────────────────────────────┐
│ Django API / Agent Stream / Approval API  │
└───────────────────────────────────────────┘
```

---

# 5. 页面与路由

第一版建议包含以下页面。

```text
/
├── /chat
├── /today
├── /calendar
├── /tasks
├── /reminders
├── /briefings
│   ├── /briefings
│   ├── /briefings/new
│   ├── /briefings/:id
│   └── /briefing-runs/:id
├── /approvals
├── /settings
│   ├── /settings/profile
│   ├── /settings/time
│   ├── /settings/notifications
│   ├── /settings/briefing
│   └── /settings/integrations
└── /login
```

---

## 5.1 Chat 页面

Chat 是主要自然语言交互入口。

页面布局建议：

```text
┌────────────────────────────────────────────────────┐
│ 顶部栏：会话标题 / 时区 / Agent 状态               │
├──────────────────────────────┬─────────────────────┤
│                              │                     │
│ 对话消息区                   │ 今日上下文侧栏      │
│                              │                     │
│ 用户消息                     │ 下一个日程          │
│ Agent 消息                    │ 今日任务            │
│ Tool 状态                    │ 待审批操作          │
│ 审批卡片                     │ 当前时间            │
│ 简报卡片                     │                     │
│                              │                     │
├──────────────────────────────┴─────────────────────┤
│ 输入框 / 附加操作 / 发送按钮                       │
└────────────────────────────────────────────────────┘
```

移动端将右侧栏折叠为抽屉。

Chat 页面支持：

* 新建会话；
* 切换历史会话；
* SSE 流式回答；
* Tool 状态展示；
* Handoff 状态展示；
* 审批卡片；
* 结构化日程卡片；
* 简报结果；
* 重试失败请求；
* 停止当前生成；
* 复制或导出回答。

---

## 5.2 Today 页面

Today 页面是结构化的每日工作台。

建议包含：

```text
今日概览
├── 当前日期与天气
├── 下一个日程
├── 今日日程时间线
├── 今日计划任务
├── 今日截止任务
├── 已逾期任务
├── 待处理提醒
├── 待审批操作
└── 最新晨报
```

Today 页面不依赖 Agent 才能加载。

页面数据直接来自后端业务 API。

---

## 5.3 Calendar 页面

Calendar 页面支持：

* 月视图；
* 周视图；
* 日视图；
* 日程拖拽；
* 日程时间调整；
* 全天事件；
* 本地日历和外部日历区分；
* 冲突提示；
* 事件详情抽屉；
* 创建、编辑和取消日程；
* 重复事件范围选择。

拖拽修改时间属于高风险写操作时，应先创建或请求后端生成 ActionProposal，而不是直接静默保存。

例如拖拽后弹出：

```text
将“项目会议”从 14:00–15:00
调整为 15:00–16:00？

发现冲突：
15:30–16:00 代码评审
```

---

## 5.4 Tasks 页面

Tasks 页面支持：

* Inbox；
* 今日任务；
* 即将到期；
* 已逾期；
* 已计划；
* 进行中；
* 已完成；
* 按项目分组；
* 优先级；
* 标签；
* 预计时长；
* 计划执行时间；
* 截止时间。

必须在界面中明确区分：

```text
截止时间 due_at
```

和：

```text
计划执行时间 planned_start_at / planned_end_at
```

避免用户把二者混淆。

---

## 5.5 Reminders 页面

Reminders 页面支持：

* 待发送；
* 已发送；
* 发送失败；
* 已取消；
* 重试状态；
* 通知渠道；
* 关联日程或任务；
* 创建自定义提醒；
* 取消提醒；
* 查看失败原因。

状态需要使用明确文案：

```text
等待发送
已进入队列
正在发送
发送成功
发送失败
已取消
```

---

## 5.6 Briefings 页面

Briefings 页面分为配置和运行结果两部分。

### 简报配置

支持配置：

* 简报名；
* 是否启用；
* 执行时间；
* 时区；
* 周期；
* 简报 Section；
* 新闻主题；
* 天气位置；
* 内容风格；
* 通知渠道；
* 失败时是否发送部分简报。

Section 使用可排序列表：

```text
1. 今日日程
2. 到期任务
3. 三天天气
4. AI 新闻
5. GitHub 动态
```

用户可以：

* 增加 Section；
* 删除 Section；
* 拖拽排序；
* 修改 Section 参数；
* 预览简报；
* 立即运行。

### 简报运行结果

展示：

* 运行状态；
* 计划执行时间；
* 实际开始和结束时间；
* 最终简报；
* 原始 Section 数据；
* 来源链接；
* 警告；
* 发送结果；
* 失败原因；
* 重新生成按钮。

---

## 5.7 Approvals 页面

Approvals 页面集中展示：

* 等待审批；
* 已批准；
* 已拒绝；
* 已执行；
* 已过期；
* 执行失败。

审批详情包括：

* 用户原始请求；
* Agent 解释；
* 操作类型；
* 变更前后数据；
* 冲突信息；
* 风险等级；
* 影响范围；
* 创建时间；
* 过期时间。

用户可以：

```text
批准
编辑后批准
拒绝
```

审批提交后，前端应继续订阅或轮询执行结果。

---

## 5.8 Settings 页面

设置页面至少包含：

### 时间偏好

* 时区；
* 工作日；
* 工作时间；
* 睡眠时间；
* 默认事件时长；
* 默认提醒时间；
* 专注时段；
* 不希望安排事务的时间；
* 周末规则。

### 通知偏好

* 浏览器通知；
* 邮件；
* Telegram；
* 提醒提前量；
* 失败通知；
* 简报发送渠道。

### 简报偏好

* 默认语言；
* 简洁程度；
* 新闻主题；
* 天气位置；
* 是否包含建议；
* 是否显示来源。

### 外部集成

* Google Calendar；
* CalDAV；
* Gmail；
* GitHub；
* Telegram；
* 其他 Provider。

集成状态需要显示：

```text
未连接
连接中
已连接
Token 即将过期
连接失败
需要重新授权
```

---

# 6. 前端目录结构

```text
frontend/
├── README.md
├── Dockerfile
├── nginx.conf
├── package.json
├── vite.config.ts
├── tsconfig.json
├── .env.example
│
├── public/
│
├── src/
│   ├── main.tsx
│   ├── app/
│   │   ├── router.tsx
│   │   ├── providers.tsx
│   │   ├── query-client.ts
│   │   └── error-boundary.tsx
│   │
│   ├── layouts/
│   │   ├── app-layout.tsx
│   │   ├── auth-layout.tsx
│   │   └── mobile-navigation.tsx
│   │
│   ├── pages/
│   │   ├── chat-page.tsx
│   │   ├── today-page.tsx
│   │   ├── calendar-page.tsx
│   │   ├── tasks-page.tsx
│   │   ├── reminders-page.tsx
│   │   ├── briefings-page.tsx
│   │   ├── briefing-run-page.tsx
│   │   ├── approvals-page.tsx
│   │   └── settings-page.tsx
│   │
│   ├── features/
│   │   ├── chat/
│   │   │   ├── api/
│   │   │   ├── components/
│   │   │   ├── hooks/
│   │   │   ├── store/
│   │   │   ├── types/
│   │   │   └── utils/
│   │   │
│   │   ├── events/
│   │   ├── tasks/
│   │   ├── reminders/
│   │   ├── planning/
│   │   ├── approvals/
│   │   ├── briefings/
│   │   ├── settings/
│   │   └── integrations/
│   │
│   ├── components/
│   │   ├── ui/
│   │   ├── feedback/
│   │   ├── date-time/
│   │   ├── status/
│   │   └── navigation/
│   │
│   ├── api/
│   │   ├── client.ts
│   │   ├── generated/
│   │   ├── errors.ts
│   │   ├── auth.ts
│   │   └── sse.ts
│   │
│   ├── hooks/
│   ├── stores/
│   ├── schemas/
│   ├── types/
│   ├── utils/
│   │   ├── datetime.ts
│   │   ├── timezone.ts
│   │   ├── formatting.ts
│   │   └── idempotency.ts
│   │
│   └── styles/
│
├── tests/
│   ├── unit/
│   ├── components/
│   └── e2e/
│
└── scripts/
    └── generate-api-types.sh
```

---

# 7. 状态管理

前端状态划分为三类。

## 7.1 服务端业务状态

由 TanStack Query 管理：

* Events；
* Tasks；
* Reminders；
* Briefings；
* BriefingRuns；
* ActionProposals；
* UserPreference；
* Integrations。

负责：

* 缓存；
* 请求去重；
* 失效刷新；
* Mutation；
* 错误状态；
* 乐观更新。

高风险操作不建议进行不可恢复的乐观更新。

---

## 7.2 Agent 流状态

Agent 流状态独立管理：

```text
idle
connecting
running
waiting_for_tool
waiting_for_approval
handing_off
completed
failed
cancelled
```

同时保存：

* 当前 Agent；
* 当前 Run ID；
* 当前消息；
* Tool 执行状态；
* 待审批 Proposal；
* SSE 连接状态；
* 最后事件序号。

可使用 Zustand 管理。

---

## 7.3 界面状态

例如：

* 侧栏是否展开；
* 当前日历视图；
* 当前筛选器；
* 移动端抽屉；
* 编辑弹窗；
* 当前选择的任务；
* 简报 Section 排序草稿。

这类状态不写入服务端。

---

# 8. API Client

前端应建立统一 API Client。

必须支持：

* 基础 URL；
* Cookie 或 Token；
* CSRF；
* 请求 ID；
* 超时；
* 错误映射；
* 401 自动处理；
* 幂等键；
* AbortController；
* OpenAPI 生成类型。

禁止在页面组件中直接散落：

```typescript
fetch("/api/...")
```

统一调用：

```typescript
apiClient.events.list(...)
apiClient.tasks.create(...)
apiClient.approvals.approve(...)
```

---

## 8.1 OpenAPI 类型同步

Django 后端应提供 OpenAPI Schema。

前端构建或开发时生成：

```text
src/api/generated/
```

生成内容包括：

* Request 类型；
* Response 类型；
* Enum；
* API Client 方法。

前后端不得各自手写两套不一致的类型定义。

---

# 9. Chat 与 SSE

## 9.1 Chat 请求流程

```text
用户发送消息
    ↓
POST /api/v1/chat/messages
    ↓
后端返回 run_id 或建立 SSE
    ↓
前端订阅流事件
    ↓
实时更新消息与 Agent 状态
    ↓
完成后刷新相关业务数据
```

---

## 9.2 SSE 事件类型

前端至少处理：

```text
message.started
agent.started
agent.status
agent.plan_updated

tool.started
tool.completed
tool.failed

handoff.started
handoff.completed

approval.required
approval.received

message.delta
message.completed

run.completed
run.failed
run.cancelled
```

建议统一事件结构：

```typescript
type AgentStreamEvent = {
  id: string;
  type: string;
  runId: string;
  conversationId?: string;
  timestamp: string;
  data: unknown;
};
```

---

## 9.3 SSE 断线处理

前端需要支持：

* 自动重连；
* 保存最后事件 ID；
* 页面刷新后恢复；
* Run 已结束时停止重连；
* 避免重复追加相同事件；
* 显示连接中断提示。

后端应允许通过：

```text
Last-Event-ID
```

或事件游标恢复流。

---

## 9.4 Tool 状态展示

Tool Call 不展示模型私有推理，只展示可理解的执行状态。

例如：

```text
正在读取 7 月 15 日到 7 月 21 日的日程
已找到 6 个日程

正在搜索 60 分钟空闲时间
已找到 4 个候选时间

正在检查冲突
发现 1 个潜在冲突
```

不要展示：

* 模型 Chain of Thought；
* 内部隐藏 Prompt；
* API Key；
* 完整敏感参数；
* 不适合用户理解的底层错误栈。

---

# 10. ActionProposal 审批交互

## 10.1 审批卡片

审批卡片应根据操作类型使用专用展示。

### 创建日程

```text
创建 2 个日程

周二 19:00–20:00 健身
周四 19:00–20:00 健身

时区：Asia/Singapore
提醒：提前 30 分钟
冲突：无
```

### 修改日程

```text
修改“项目会议”

原时间：14:00–15:00
新时间：15:00–16:00

影响：仅此事件
冲突：与代码评审重叠 30 分钟
```

---

## 10.2 编辑后批准

用户选择“编辑后批准”时，应打开结构化表单。

编辑完成后调用：

```text
POST /api/v1/action-proposals/{id}/edit
```

后端重新：

* 校验；
* 检查冲突；
* 计算风险；
* 更新 Proposal。

如果修改导致风险变化，可能需要再次确认。

---

## 10.3 审批状态

前端处理：

```text
awaiting_approval
approved
rejected
executing
executed
failed
expired
```

如果 Proposal 已过期，批准按钮必须禁用，并提示重新生成。

---

# 11. 数据刷新策略

当 Tool 或审批操作改变业务数据后，前端应使相关 Query 失效。

例如：

### 创建日程成功

刷新：

```text
events
today-summary
conflicts
pending-approvals
```

### 完成任务成功

刷新：

```text
tasks
today-summary
briefing-preview
```

### 更新用户偏好

刷新：

```text
user-preferences
planning-recommendations
briefing-configurations
```

不要每次都刷新整个应用。

---

# 12. 时间和时区处理

前端建立统一时间工具层。

禁止在组件中到处直接调用：

```typescript
new Date(...)
```

统一实现：

```text
parseApiDateTime
formatInUserTimezone
toUtcISOString
formatDateRange
isAllDayEvent
getTimezoneLabel
```

前端表单需要区分：

* 日期；
* 本地时间；
* 时区；
* UTC 时间。

提交时：

```text
用户输入的本地时间
    +
用户选择的 IANA 时区
    ↓
转换为 UTC
    ↓
同时提交原始 timezone
```

---

# 13. 身份认证与安全

第一版推荐使用 Django Session + HttpOnly Cookie。

优点：

* 浏览器不直接保存访问 Token；
* 可使用 Django CSRF；
* 同域部署简单；
* 适合自托管 Web 应用。

前端需要处理：

* 登录失效；
* 401 跳转；
* CSRF Token；
* 权限不足；
* 外部 OAuth 回调；
* 敏感页面保护。

禁止：

* 将 API Key 保存到 localStorage；
* 在浏览器暴露 LLM Provider Key；
* 在前端直接调用需要密钥的天气、新闻或模型 API；
* 在日志中打印认证 Cookie。

---

# 14. 错误处理

错误需要分层展示。

## 14.1 表单错误

直接显示在字段附近：

```text
结束时间必须晚于开始时间。
```

## 14.2 业务错误

使用可理解的业务文案：

```text
该日程已经被其他操作修改，请刷新后重试。
```

```text
这个时间与现有会议冲突。
```

## 14.3 Provider 错误

例如天气失败：

```text
天气数据暂时不可用，其他简报内容已正常生成。
```

## 14.4 Agent 错误

例如调用限制：

```text
Agent 已达到本次执行上限，已保留当前计划草案，没有执行未完成的操作。
```

## 14.5 未知错误

展示 Request ID，方便排查：

```text
操作失败，请稍后重试。
请求编号：req_xxx
```

不要向用户显示后端堆栈。

---

# 15. 响应式设计

前端优先支持：

* 桌面浏览器；
* 平板；
* 手机浏览器。

桌面布局：

```text
左侧导航 + 主内容 + 可选右侧上下文栏
```

移动布局：

```text
顶部栏 + 主内容 + 底部导航 + 抽屉
```

移动端底部导航建议：

```text
今天
聊天
日历
任务
更多
```

第一版可以提供 PWA Manifest，但不要求实现完整离线写入能力。

---

# 16. 浏览器通知

前端可以支持浏览器通知，但它只能作为通知渠道之一。

流程：

```text
用户授权浏览器通知
    ↓
前端注册 Push Subscription
    ↓
提交给后端
    ↓
后端保存设备订阅
    ↓
Reminder Dispatcher 发送 Web Push
```

浏览器页面关闭后仍要接收通知时，应使用 Web Push，而不是仅使用页面内定时器。

禁止依赖：

```typescript
setTimeout(...)
```

实现真实提醒。

---

# 17. 前后端同步部署

推荐采用同域部署：

```text
https://time-agent.example.com/
    ├── /              前端静态文件
    ├── /api/          Django REST API
    ├── /api/v1/chat/  Chat API
    ├── /events/       SSE
    ├── /admin/        Django Admin
    └── /static/       Django 静态资源
```

Nginx 负责：

* 前端静态文件；
* SPA 路由回退；
* `/api/` 反向代理；
* SSE 反向代理；
* Django Admin；
* 静态文件；
* TLS。

---

## 17.1 Docker Compose 拓扑

```text
docker-compose.yml
├── frontend
├── nginx
├── django
├── celery-worker
├── celery-beat
├── postgres
└── redis
```

推荐生产部署：

```text
frontend 容器
    ↓ 构建 React 静态文件
Nginx 容器
    ↓ 提供静态文件
    ↓ 代理 Django
```

也可以使用多阶段构建，将前端产物直接复制到 Nginx 镜像。

---

## 17.2 SSE 的 Nginx 配置要求

SSE 路径必须：

* 关闭代理缓冲；
* 设置较长超时；
* 保持连接；
* 禁止响应压缩造成缓存问题。

示意：

```nginx
location /events/ {
    proxy_pass http://django:8000;

    proxy_http_version 1.1;
    proxy_set_header Connection "";

    proxy_buffering off;
    proxy_cache off;

    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;

    add_header X-Accel-Buffering no;
}
```

Chat SSE 路径也可以统一放在：

```text
/api/v1/chat/runs/{run_id}/events
```

---

## 17.3 SPA 路由回退

Nginx 需要支持 React Router：

```nginx
location / {
    try_files $uri $uri/ /index.html;
}
```

但以下路径不能回退到前端：

```text
/api/
/admin/
/static/
/media/
/events/
```

---

# 18. 前端环境变量

`.env.example`：

```text
VITE_APP_NAME=Time Agent

VITE_API_BASE_URL=/api/v1
VITE_SSE_BASE_URL=/api/v1

VITE_DEFAULT_LOCALE=zh-CN
VITE_DEFAULT_TIMEZONE=Asia/Singapore

VITE_ENABLE_BROWSER_NOTIFICATIONS=true
VITE_ENABLE_CALENDAR=true
VITE_ENABLE_BRIEFINGS=true
VITE_ENABLE_EXTERNAL_INTEGRATIONS=false

VITE_SENTRY_DSN=
VITE_BUILD_VERSION=
```

任何敏感密钥都不能放入 `VITE_*` 环境变量，因为它们会进入浏览器构建产物。

---

# 19. 前端测试策略

## 19.1 单元测试

测试：

* 日期和时区转换；
* SSE 事件 Reducer；
* Agent 状态转换；
* API 错误映射；
* ActionProposal 表单转换；
* Briefing Section 配置；
* Query Key 生成；
* 幂等键生成。

---

## 19.2 组件测试

测试：

* Chat Message；
* Tool Status；
* Approval Card；
* Event Editor；
* Task Form；
* Reminder Status；
* Briefing Editor；
* Timezone Selector；
* Error State；
* Loading Skeleton。

---

## 19.3 端到端测试

使用 Playwright 测试：

```text
用户登录
用户发送“今天有什么安排”
SSE 返回 Tool 状态
Agent 返回日程结果

用户请求创建日程
前端展示 Approval Card
用户批准
日程出现在 Calendar 页面

用户点击立即生成简报
Briefing Workflow 执行
前端显示简报内容

用户断开并重新加载页面
继续查看未完成 Agent Run
```

---

## 19.4 Mock 策略

前端开发环境需要提供：

* Mock REST API；
* Mock SSE Stream；
* Mock ActionProposal；
* Mock BriefingRun；
* Mock Provider Failure；
* Mock Agent Limit Reached。

可以使用 MSW 模拟后端。

---

# 20. 前端开发阶段

## 阶段 F0：前端骨架

完成：

* React + TypeScript + Vite；
* Router；
* App Layout；
* API Client；
* TanStack Query；
* Zustand；
* Tailwind；
* 基础组件；
* Dockerfile；
* Nginx 配置。

---

## 阶段 F1：认证和基础布局

完成：

* 登录页；
* Session 检查；
* 401 处理；
* 左侧导航；
* 移动端导航；
* 用户时区显示；
* 全局错误边界。

---

## 阶段 F2：传统事务界面

完成：

* Today 页面；
* Calendar 页面；
* Tasks 页面；
* Reminders 页面；
* 基础 CRUD；
* 时间表单；
* 后端业务错误展示。

此阶段可以暂不接 Agent。

---

## 阶段 F3：Chat 和 SSE

完成：

* Conversation UI；
* 消息发送；
* SSE 连接；
* Agent 状态；
* Tool 状态；
* 流式回答；
* 断线恢复；
* 停止运行；
* 历史会话。

---

## 阶段 F4：审批流程

完成：

* ActionProposal Card；
* Approvals 页面；
* 批准；
* 编辑后批准；
* 拒绝；
* 执行状态；
* Proposal 过期处理。

---

## 阶段 F5：简报界面

完成：

* BriefingDefinition 列表；
* Section 编辑器；
* 立即运行；
* BriefingRun 页面；
* 来源展示；
* 部分失败展示；
* 通知渠道配置。

---

## 阶段 F6：外部集成

完成：

* Google Calendar 连接状态；
* CalDAV 配置；
* Telegram；
* Gmail；
* GitHub；
* OAuth 回调页面；
* 重新授权流程。

---

## 阶段 F7：移动端和 PWA

完成：

* 响应式优化；
* PWA Manifest；
* Web Push；
* 安装提示；
* 移动端日历；
* 移动端审批流程。

---

# 21. 前端 Vibe Coding 约束

## 21.1 按 Feature 开发

推荐任务：

```text
实现 ActionProposalCard 组件及其组件测试。
只允许修改：
src/features/approvals/
tests/components/approvals/
```

不推荐：

```text
把整个前端做出来。
```

---

## 21.2 页面组件不直接调用 Fetch

统一通过：

```text
feature api
    ↓
shared api client
```

页面组件只调用 Hook。

---

## 21.3 不在前端复制后端业务规则

前端不得自行实现：

* 风险等级计算；
* 日程冲突最终判断；
* Proposal 是否允许执行；
* 提醒幂等；
* 任务状态机；
* 外部日历版本冲突。

---

## 21.4 所有时间使用统一工具

禁止在业务组件中分散编写时区转换逻辑。

---

## 21.5 SSE 事件必须集中处理

所有事件通过统一 Stream Client 和 Reducer 处理。

禁止每个页面分别解析 SSE。

---

## 21.6 新增 API 必须同步 OpenAPI 类型

不允许长期使用：

```typescript
any
```

绕过后端类型。

---

## 21.7 Agent UI 不显示私有推理

前端只展示：

* 工具状态；
* 执行进度；
* 计划结果；
* 审批内容；
* 可公开错误。

不展示模型私有推理过程。

---

# 22. 前端 MVP 验收标准

## 基础事务

* 用户可以查看今日日程；
* 用户可以查看任务和提醒；
* 用户可以创建和编辑普通事务；
* 所有时间按用户时区显示。

## Agent 交互

* 用户可以发送自然语言消息；
* 前端可以流式显示 Agent 回答；
* Tool 执行状态可见；
* Handoff 状态可见；
* SSE 断线可以恢复。

## 审批

* 高风险操作显示结构化审批卡片；
* 用户可以批准、编辑或拒绝；
* 执行完成后相关页面自动刷新；
* 过期 Proposal 不能继续执行。

## 简报

* 用户可以配置简报；
* 用户可以手动运行；
* 可以查看结构化 Section；
* 可以查看来源；
* 单个 Section 失败不会阻止其他内容展示。

## 部署

* 前端和后端可以通过 Docker Compose 同步启动；
* Nginx 正确代理 API 和 SSE；
* SPA 路由刷新不会返回 404；
* 浏览器中不暴露任何服务端密钥。

---

# 23. 最终前端职责边界

```text
React 页面
负责展示与交互

TanStack Query
负责服务端状态和缓存

Zustand
负责 Agent 流和界面状态

API Client
负责与 Django 通信

SSE Client
负责 Agent 实时事件

Approval UI
负责收集用户决策

Django API
负责业务操作

Application Service
负责业务规则

LangGraph
负责 Agent 执行与工作流

Celery
负责定时任务和提醒

PostgreSQL
负责保存权威事实
```

前端负责让 Agent 的行为透明、可控、可修改，但不能绕过后端直接决定真实业务状态。
