# Time Agent 项目架构规范

> 文档版本：v0.2
> 项目阶段：架构设计 / MVP 准备
> 核心框架：Django + PostgreSQL + Celery + LangChain + LangGraph

---

# 1. 项目定位

Time Agent 是一个以时间为核心的个人智能事务管理系统。

系统通过自然语言帮助用户完成：

* 日程创建、查询、修改和冲突检查；
* 任务、计划与截止时间管理；
* 提醒创建和准时触发；
* 空闲时间搜索与事务安排；
* 短期计划制订和动态修订；
* 每日、每周和自定义简报生成；
* 天气、新闻、GitHub、邮件等外部信息汇总；
* 长期偏好和个人时间习惯管理。

系统不是普通聊天机器人，而是：

```text
自然语言交互层
        +
可靠的事务管理系统
        +
确定性的时间调度系统
        +
可扩展的信息简报平台
        +
有状态的智能规划 Agent
```

---

# 2. 核心设计原则

## 2.1 大模型不负责计时

大模型负责：

* 理解自然语言；
* 提取时间约束；
* 查询相关数据；
* 制订计划；
* 根据工具结果修订计划；
* 选择下一步操作；
* 生成自然语言回答。

数据库和调度器负责：

* 保存日程、任务和提醒；
* 准时触发提醒；
* 执行周期任务；
* 去重；
* 失败重试；
* 状态记录。

禁止依赖大模型“记住”某个提醒。

---

## 2.2 PostgreSQL 是业务事实来源

所有真实业务状态必须保存在 PostgreSQL：

* 日程；
* 任务；
* 提醒；
* 用户偏好；
* 简报配置；
* 简报运行结果；
* Agent 提出的操作；
* 用户审批结果；
* 实际执行结果。

聊天记录、Agent Memory 和向量数据库不能替代业务数据库。

---

## 2.3 Agent 不直接操作 ORM

统一调用链：

```text
Agent
  ↓
Agent Tool
  ↓
Application Service
  ↓
Domain Model / Repository
  ↓
Django ORM
  ↓
PostgreSQL
```

禁止：

```text
Prompt
  ↓
Agent 节点直接访问或修改 Django ORM
```

---

## 2.4 外层 Graph 保持轻量

外层 LangGraph 不负责拆解主 Agent 的每一步内部思考。

外层 Graph 主要负责：

* 区分触发来源；
* 将请求路由到正确工作流；
* 控制 Agent 之间的转交；
* 管理确定性流程；
* 管理子图；
* 管理中断和恢复；
* 管理不同持久化边界。

主 Agent 内部的：

* 理解；
* 查询；
* 规划；
* 工具调用；
* 结果观察；
* 计划修订；
* 最终回答；

由 `create_agent()` 创建的 Agent Loop 完成。

---

## 2.5 确定性逻辑和 Agent 逻辑分离

适合放入确定性 Python 代码的逻辑：

* 时间合法性判断；
* 日程冲突检测；
* 空闲时间搜索；
* 权限检查；
* 任务状态转换；
* 提醒去重；
* 数据保存；
* 外部通知发送；
* 新闻条目去重；
* 时区转换。

适合交给 Agent 的逻辑：

* 理解模糊请求；
* 决定需要查询哪些信息；
* 根据多个约束制订计划；
* 根据工具结果修订方案；
* 判断哪些内容适合进入简报；
* 综合多个事实生成文字；
* 与用户协商安排。

---

## 2.6 写操作必须可审计

所有改变真实状态的操作都应记录：

* 用户原始请求；
* 提出操作的 Agent；
* 操作类型；
* 操作参数；
* 风险等级；
* 是否需要审批；
* 用户审批结果；
* 实际执行时间；
* 执行结果；
* 错误信息；
* 幂等键。

---

## 2.7 外部能力必须可替换

天气、新闻、日历、邮件、通知渠道和模型调用均通过 Provider 接口接入。

例如：

```text
WeatherProvider
├── OpenMeteoProvider
├── WeatherAPIProvider
└── MockWeatherProvider
```

业务层不能直接依赖某一个具体平台。

---

# 3. MVP 范围

第一版只完成以下四个完整闭环。

## 3.1 创建提醒

用户输入：

```text
明天下午三点提醒我提交报告。
```

系统完成：

1. 加载当前时间和用户时区；
2. 解析相对时间；
3. 将时间转换为明确的绝对时间；
4. 创建提醒记录；
5. 到达时间后发送通知；
6. 记录发送结果；
7. 防止重复发送。

---

## 3.2 查询今日安排

用户输入：

```text
我今天有什么安排？
```

系统返回：

* 今日日程；
* 今日计划执行的任务；
* 今日截止任务；
* 已逾期任务；
* 时间冲突；
* 距离下一个日程的时间。

---

## 3.3 安排空闲时间

用户输入：

```text
这周帮我找两个晚上健身，每次一小时。
```

系统完成：

1. 查询本周已有安排；
2. 加载用户作息和偏好；
3. 搜索候选空闲时间；
4. 对候选时间进行评分；
5. 生成安排草案；
6. 与用户协商或修订；
7. 用户确认后写入日程。

---

## 3.4 每日晨间简报

每天固定时间生成：

* 今日日期；
* 今日日程；
* 到期和逾期任务；
* 未来几天天气；
* 用户关注的新闻；
* 时间冲突；
* 风险提示；
* 今日建议。

---

# 4. 第一版不做的功能

第一版暂不实现：

* 大规模多 Agent 自组织协作；
* Agent 自行无限循环；
* 自动修改他人日历；
* 复杂团队权限系统；
* 自动发送会议邀请；
* 自动回复邮件；
* 大规模网页爬虫；
* 完整项目管理平台；
* 自动重排用户全部日程；
* 强化学习时间规划；
* 原生移动端应用；
* 语音助手；
* 复杂组织级工作流。

第一版采用：

```text
薄外层 Graph
    +
一个主 Time Steward Agent
    +
一个 Briefing Workflow
    +
若干确定性工具和节点
```

---

# 5. 技术栈

| 模块               | 技术选择                       |
| ---------------- | -------------------------- |
| 后端               | Django                     |
| API              | Django REST Framework      |
| 数据库              | PostgreSQL                 |
| 缓存与消息代理          | Redis                      |
| 异步任务             | Celery                     |
| 周期调度             | Celery Beat                |
| Agent 高层 API     | LangChain `create_agent`   |
| Agent 编排         | LangGraph `StateGraph`     |
| Agent Middleware | LangChain Agent Middleware |
| 短期状态             | LangGraph Checkpointer     |
| 长期记忆             | LangGraph Store            |
| 数据校验             | Pydantic                   |
| 模型调用             | OpenAI Compatible Adapter  |
| 流式响应             | SSE                        |
| 管理后台             | Django Admin               |
| 监控指标             | Prometheus                 |
| 仪表盘              | Grafana                    |
| 日志               | JSON Structured Logging    |
| 本地部署             | Docker Compose             |

项目初始化时应锁定经过验证的 LangChain、LangGraph 和 Checkpointer 版本，并通过锁文件固定完整依赖。

---

# 6. 总体系统架构

```text
┌─────────────────────────────────────────────┐
│                 触发入口                    │
│                                             │
│ Chat UI / REST API / Celery / Webhook       │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│              Trigger Envelope               │
│                                             │
│ user_message                                │
│ scheduled_briefing                          │
│ manual_briefing                             │
│ reminder_due                                │
│ calendar_webhook                            │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│             Outer LangGraph                 │
│                                             │
│ normalize_runtime_context                   │
│ deterministic_router                        │
│ handoff / subgraph orchestration            │
└──────────────┬─────────────┬────────────────┘
               │             │
               ▼             ▼
┌──────────────────────┐  ┌──────────────────────┐
│ Time Steward Agent   │  │ Briefing Workflow    │
│                      │  │                      │
│ create_agent()       │  │ Data Collectors      │
│ Middleware           │  │ News Research Agent  │
│ Tools                │  │ Editor Agent         │
│ Agent Loop           │  │ Validation           │
└──────────┬───────────┘  └──────────┬───────────┘
           │                         │
           └──────────────┬──────────┘
                          ▼
┌─────────────────────────────────────────────┐
│             Application Services            │
│                                             │
│ EventService                                │
│ TaskService                                 │
│ ReminderService                             │
│ PlanningService                             │
│ BriefingService                             │
└──────────────────────┬──────────────────────┘
                       ▼
┌─────────────────────────────────────────────┐
│              Domain Layer                   │
│                                             │
│ CalendarEvent                               │
│ Task                                        │
│ Reminder                                    │
│ UserPreference                              │
│ BriefingDefinition                          │
│ BriefingRun                                 │
│ ActionProposal                              │
└──────────────────────┬──────────────────────┘
                       ▼
┌─────────────────────────────────────────────┐
│ PostgreSQL / Redis / Celery                 │
└──────────────────────┬──────────────────────┘
                       ▼
┌─────────────────────────────────────────────┐
│ External Providers                          │
│                                             │
│ Weather / News / Calendar / Gmail           │
│ GitHub / MMKB / Notification Channels       │
└─────────────────────────────────────────────┘
```

---

# 7. Agent 系统设计

## 7.1 Agent 划分原则

仅在以下情况拆分新的 Agent：

* 工具集合明显属于不同领域；
* 不同能力需要完全不同的 System Prompt；
* 上下文过长；
* 某个领域需要独立的循环和评估；
* 某个能力需要单独的持久化策略；
* 某个能力需要独立的安全边界。

第一版包含：

```text
Agent 1：Time Steward Agent
Agent 2：Briefing Editor Agent
可选 Agent 3：News Research Agent
```

天气查询、日程查询和任务查询不是独立 Agent，而是工具或确定性节点。

---

## 7.2 Time Steward Agent

Time Steward Agent 是长期、有状态、直接与用户交互的主 Agent。

使用：

```python
create_agent(...)
```

创建。

它负责：

* 理解用户请求；
* 读取当前时间和时区；
* 查询用户偏好；
* 查询日程、任务和提醒；
* 识别缺失信息；
* 制订时间计划；
* 调用冲突检测；
* 搜索空闲时间；
* 创建或修改任务；
* 创建提醒；
* 提出日程变更方案；
* 根据用户反馈修订计划；
* 转交简报生成请求；
* 输出最终回答。

其内部执行过程是 Agent Loop：

```text
用户请求
   ↓
模型决定下一步
   ↓
调用工具
   ↓
观察工具结果
   ↓
重新规划
   ↓
继续调用工具或完成任务
   ↓
最终回答
```

外层 Graph 不为这个内部循环建立单独节点。

---

## 7.3 Briefing Workflow

简报能力不设计成一个完全自由运行的大 Agent。

简报采用：

```text
确定性数据收集
        +
专业 Agent 内容处理
        +
确定性校验和投递
```

整体流程：

```text
load_briefing_definition
        ↓
collect_sections
 ┌──────┼─────────┬────────────┐
 │      │         │            │
 ▼      ▼         ▼            ▼
日程    任务      天气      新闻研究
节点    节点      节点       Agent
 │      │         │            │
 └──────┴─────────┴────────────┘
                 ↓
normalize_and_deduplicate
                 ↓
Briefing Editor Agent
                 ↓
validate_briefing
                 ↓
persist_briefing_run
                 ↓
deliver_briefing
```

其中：

### 确定性节点负责

* 读取日程；
* 读取任务；
* 获取天气；
* 新闻条目去重；
* 时间排序；
* 检查来源；
* 保存简报；
* 发送通知。

### Agent 节点负责

* 新闻相关性判断；
* 新闻内容综合；
* 选择简报重点；
* 分析天气对计划的影响；
* 生成自然语言简报；
* 根据用户风格组织内容。

---

## 7.4 用户请求简报

```text
用户：生成一份今天的晨报
        ↓
Time Steward Agent
        ↓
transfer_to_briefing
        ↓
Briefing Workflow
        ↓
返回结果给 Time Steward Agent 或用户
```

---

## 7.5 定时生成简报

```text
Celery Beat
        ↓
TriggerEnvelope(
    type="scheduled_briefing"
)
        ↓
deterministic_router
        ↓
Briefing Workflow
        ↓
保存并发送
```

定时简报不需要先调用 Time Steward Agent 判断意图。

触发类型已经明确，因此直接进入 Briefing Workflow。

---

# 8. Trigger Envelope

所有进入 Agent 系统的请求统一封装为 Trigger Envelope。

```python
class TriggerEnvelope(BaseModel):
    trigger_type: Literal[
        "user_message",
        "manual_briefing",
        "scheduled_briefing",
        "reminder_due",
        "calendar_webhook",
    ]

    user_id: UUID
    request_id: UUID
    conversation_id: UUID | None = None

    payload: dict
    triggered_at: datetime
```

示例：

```json
{
  "trigger_type": "scheduled_briefing",
  "user_id": "user-uuid",
  "request_id": "request-uuid",
  "conversation_id": null,
  "payload": {
    "briefing_definition_id": "briefing-uuid"
  },
  "triggered_at": "2026-07-15T00:00:00Z"
}
```

---

# 9. 外层 LangGraph

## 9.1 Graph 流程

```text
START
  ↓
normalize_runtime_context
  ↓
route_by_trigger
  │
  ├── user_message
  │       ↓
  │   Time Steward Agent
  │       │
  │       ├── final response → END
  │       │
  │       └── handoff
  │               ↓
  │        Briefing Workflow
  │               ↓
  │              END
  │
  ├── manual_briefing
  │       ↓
  │   Briefing Workflow
  │       ↓
  │      END
  │
  ├── scheduled_briefing
  │       ↓
  │   Briefing Workflow
  │       ↓
  │      END
  │
  ├── reminder_due
  │       ↓
  │   Reminder Dispatcher
  │       ↓
  │      END
  │
  └── calendar_webhook
          ↓
      Calendar Sync Workflow
          ↓
         END
```

---

## 9.2 Graph 示例

```python
from langgraph.graph import END, START, StateGraph


def route_trigger(state: AppState) -> str:
    trigger_type = state["trigger_type"]

    routes = {
        "user_message": "time_steward_agent",
        "manual_briefing": "briefing_workflow",
        "scheduled_briefing": "briefing_workflow",
        "reminder_due": "reminder_dispatcher",
        "calendar_webhook": "calendar_sync_workflow",
    }

    return routes[trigger_type]


builder = StateGraph(AppState)

builder.add_node(
    "normalize_runtime_context",
    normalize_runtime_context,
)

builder.add_node(
    "time_steward_agent",
    time_steward_agent,
)

builder.add_node(
    "briefing_workflow",
    briefing_workflow,
)

builder.add_node(
    "reminder_dispatcher",
    reminder_dispatcher,
)

builder.add_node(
    "calendar_sync_workflow",
    calendar_sync_workflow,
)

builder.add_edge(
    START,
    "normalize_runtime_context",
)

builder.add_conditional_edges(
    "normalize_runtime_context",
    route_trigger,
)

builder.add_edge(
    "briefing_workflow",
    END,
)

builder.add_edge(
    "reminder_dispatcher",
    END,
)

builder.add_edge(
    "calendar_sync_workflow",
    END,
)
```

---

# 10. Agent State 和 Runtime Context

## 10.1 AppState

AppState 保存 Graph 执行过程中需要持久化的状态。

```python
from typing import Literal
from typing_extensions import NotRequired, TypedDict

from langchain.agents import AgentState


class AppState(AgentState):
    trigger_type: NotRequired[
        Literal[
            "user_message",
            "manual_briefing",
            "scheduled_briefing",
            "reminder_due",
            "calendar_webhook",
        ]
    ]

    request_id: NotRequired[str]
    conversation_id: NotRequired[str]
    active_agent: NotRequired[str]

    briefing_definition_id: NotRequired[str]
    pending_action_id: NotRequired[str]

    tool_results: NotRequired[list[dict]]
    warnings: NotRequired[list[str]]
    final_response: NotRequired[str]
```

---

## 10.2 RuntimeContext

Runtime Context 表示单次调用环境，不作为长期对话事实保存。

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass
class RuntimeContext:
    user_id: str
    request_id: str

    timezone: str
    locale: str
    current_datetime: datetime

    trigger_type: str
    conversation_id: str | None = None

    read_only: bool = False
```

Runtime Context 可被：

* Agent Tool；
* Middleware；
* 动态 System Prompt；
* 审计逻辑；

读取。

---

# 11. create_agent 设计

## 11.1 主 Agent 创建方式

```python
from langchain.agents import create_agent


time_steward_agent = create_agent(
    name="time_steward",
    model=primary_model,
    tools=[
        get_current_datetime,
        get_user_preferences,
        list_events,
        get_event,
        detect_conflicts,
        find_free_slots,
        list_tasks,
        get_task,
        list_reminders,
        build_schedule_proposal,
        validate_schedule_proposal,
        create_task,
        update_task,
        complete_task,
        create_reminder,
        cancel_reminder,
        create_event,
        update_event,
        cancel_event,
        transfer_to_briefing,
    ],
    system_prompt=TIME_STEWARD_SYSTEM_PROMPT,
    state_schema=AppState,
    context_schema=RuntimeContext,
    middleware=build_time_steward_middleware(),
)
```

---

## 11.2 Agent 内部职责

Time Steward Agent 可以在一个 Agent Loop 中完成：

```text
理解请求
    ↓
读取上下文
    ↓
调用查询工具
    ↓
生成初步计划
    ↓
调用冲突检测
    ↓
根据结果修改计划
    ↓
调用写操作工具
    ↓
触发用户审批
    ↓
完成或继续修订
```

但是以下逻辑不能仅依赖模型：

* 时间是否合法；
* 是否存在冲突；
* 用户是否有权限；
* 是否发生重复执行；
* 状态转换是否允许；
* 日程是否可以删除；
* 提醒是否已经发送。

这些仍由 Application Service 校验。

---

# 12. Middleware 设计

Middleware 用于处理跨工具、跨模型调用的横切逻辑。

第一版建议启用：

```text
SummarizationMiddleware
TodoListMiddleware
HumanInTheLoopMiddleware
ModelCallLimitMiddleware
ToolCallLimitMiddleware
ToolRetryMiddleware
ModelRetryMiddleware
ModelFallbackMiddleware
```

并实现以下自定义 Middleware：

```text
RuntimeContextMiddleware
DynamicToolPolicyMiddleware
AuditMiddleware
MemoryPolicyMiddleware
```

---

## 12.1 SummarizationMiddleware

负责压缩长对话和较早的工具调用历史。

目标：

* 防止长期会话超过上下文窗口；
* 保留最近的重要消息；
* 保留未完成计划；
* 保留当前待审批操作。

摘要中不能只保存自然语言聊天，还应保留：

* 当前讨论的日期范围；
* 当前计划草案；
* 尚未完成的目标；
* 尚未审批的 ActionProposal。

---

## 12.2 TodoListMiddleware

用于让 Agent 管理自己的临时执行步骤。

例如：

```text
1. 查询下周已有日程
2. 读取用户运动偏好
3. 搜索三个候选时间
4. 检查冲突
5. 生成安排草案
```

注意：

```text
Agent Todo List
```

不等于：

```text
用户的业务 Task
```

Agent Todo 只用于一次 Agent Run 的内部规划。

用户真实任务必须保存在 Django `Task` 表中。

---

## 12.3 HumanInTheLoopMiddleware

用于在高风险 Tool 执行前暂停 Agent。

建议配置：

```python
HumanInTheLoopMiddleware(
    interrupt_on={
        "create_event": {
            "allowed_decisions": [
                "approve",
                "edit",
                "reject",
            ],
        },
        "update_event": {
            "allowed_decisions": [
                "approve",
                "edit",
                "reject",
            ],
        },
        "cancel_event": {
            "allowed_decisions": [
                "approve",
                "reject",
            ],
        },
        "create_task": False,
        "complete_task": False,
        "create_reminder": False,
        "list_events": False,
        "list_tasks": False,
    }
)
```

第一版可根据产品体验调整：

* 普通个人日程是否必须审批；
* 是否仅批量操作需要审批；
* 是否允许用户配置自动执行范围。

---

## 12.4 ModelCallLimitMiddleware

防止模型无限循环。

建议限制：

```text
单次 Agent Run 模型调用：不超过 10 次
单个 Thread 累积限制：按业务需要配置
```

达到限制后：

* 停止继续调用；
* 返回当前已完成内容；
* 明确告诉用户哪些操作尚未完成；
* 记录 `agent_limit_reached`。

---

## 12.5 ToolCallLimitMiddleware

防止 Agent 重复调用同一工具。

建议：

```text
单次 Run 总工具调用：不超过 20 次
同一写入 Tool：不超过 3 次
```

---

## 12.6 ToolRetryMiddleware

适用于：

* 天气 API 临时失败；
* 新闻接口超时；
* 外部日历接口限流；
* 网络异常。

不适用于：

* 参数校验失败；
* 权限失败；
* 用户不存在；
* 日程冲突；
* 状态转换错误。

业务错误不应盲目重试。

---

## 12.7 ModelRetryMiddleware

用于处理：

* 模型网关临时超时；
* 限流；
* 服务端错误；
* 短暂连接中断。

---

## 12.8 ModelFallbackMiddleware

可以配置：

```text
Primary Model
    ↓ 失败
Fallback Model
```

Fallback Model 应满足：

* 支持 Tool Calling；
* 支持当前 Agent State；
* 支持所需上下文长度；
* 输出能力能够满足当前 Agent。

---

## 12.9 RuntimeContextMiddleware

在每次模型调用前动态注入：

* 当前绝对时间；
* 用户时区；
* 用户语言；
* 当前触发类型；
* 是否只读；
* 当前工作时间；
* 当前睡眠时间；
* 默认日程持续时间；
* 默认提醒偏移量。

示例：

```text
Current time: 2026-07-15 10:30 Asia/Singapore
User locale: zh-CN
Trigger type: user_message
Working hours: 09:00-18:00
Sleep hours: 00:30-08:00
Read-only mode: false
```

---

## 12.10 DynamicToolPolicyMiddleware

根据当前场景动态暴露工具。

### 普通用户请求

```text
查询工具
任务工具
提醒工具
日程工具
规划工具
简报转交工具
```

### 只读模式

隐藏：

```text
create_event
update_event
cancel_event
create_task
update_task
cancel_reminder
```

### 定时简报

只暴露：

```text
list_events
list_tasks
get_weather
search_news
```

不过定时简报通常直接进入 Briefing Workflow，而不是主 Agent。

---

## 12.11 AuditMiddleware

记录：

* Agent Run；
* 模型调用；
* 工具调用；
* 工具参数；
* 工具结果摘要；
* 执行耗时；
* 审批决定；
* 错误；
* Handoff；
* Token 使用量。

敏感字段必须脱敏。

---

## 12.12 MemoryPolicyMiddleware

负责控制：

* 哪些信息可以写入长期 Memory；
* 哪些信息只能保留在当前 Thread；
* 哪些信息必须写入 Domain Database；
* 哪些信息属于敏感信息，不允许自动存储。

例如：

```text
“我通常晚上健身”
```

可以作为长期偏好。

```text
“我明天上午十点开会”
```

应写入 CalendarEvent，而不能只写入 Memory。

---

# 13. Memory 设计

系统将 Memory 划分为四层。

## 13.1 Runtime Context

生命周期：单次调用。

保存：

* 当前时间；
* 时区；
* 用户 ID；
* 请求 ID；
* Trigger Type；
* 当前权限模式。

不作为长期记忆。

---

## 13.2 Short-term Memory

生命周期：同一个 Conversation / Thread。

通过 LangGraph Checkpointer 保存。

内容包括：

* 聊天消息；
* 当前讨论的计划；
* 尚未完成的操作；
* 当前激活的 Agent；
* 待审批的 ActionProposal；
* 最近的工具结果；
* 当前简报请求。

建议：

```text
thread_id = conversation_id
```

---

## 13.3 Long-term Agent Memory

生命周期：跨 Conversation。

通过 LangGraph Store 保存。

内容包括：

* 用户表达风格；
* 长期时间偏好；
* 常见活动习惯；
* 规划偏好；
* 简报语言风格；
* 不适合结构化建模的软性信息。

示例：

```text
用户不喜欢早上八点前安排活动。
用户周末通常不安排正式工作。
用户喜欢简洁的晨报。
用户倾向在晚上进行健身。
```

建议 Namespace：

```text
("users", user_id, "preferences")
("users", user_id, "habits")
("users", user_id, "briefing_style")
```

---

## 13.4 Domain Database

生命周期：业务数据存在期间。

保存：

* CalendarEvent；
* Task；
* Reminder；
* UserPreference；
* BriefingDefinition；
* BriefingRun；
* ActionProposal。

Domain Database 是权威事实来源。

---

## 13.5 四层关系

```text
Runtime Context
    单次调用参数

Checkpointer
    当前会话和执行状态

LangGraph Store
    跨会话软性记忆

Django PostgreSQL Models
    权威业务事实
```

---

# 14. Checkpointer 和 Store

## 14.1 Time Steward Agent

Time Steward Agent 使用 PostgreSQL Checkpointer。

```text
conversation_id
    ↓
thread_id
```

同一个 Conversation 可以：

* 多轮对话；
* 暂停；
* 用户审批；
* 恢复执行；
* 继续计划修订。

---

## 14.2 Briefing Workflow

每次 BriefingRun 默认使用独立运行状态。

```text
briefing_run_id
    ↓
独立 invocation
```

不应自动把昨天的完整 Briefing Agent 对话带入今天。

需要跨次保存的内容：

* 简报风格；
* 用户主题偏好；
* 来源偏好；

保存到 UserPreference 或 Long-term Store。

---

## 14.3 Reminder Dispatcher

Reminder Dispatcher 不依赖 Agent Checkpointer。

其状态由：

* Reminder；
* DeliveryAttempt；
* Celery Task；
* 幂等键；

共同管理。

---

# 15. Agent Handoff

## 15.1 Handoff 场景

Time Steward Agent 可以把请求移交给：

```text
Briefing Workflow
```

后续可扩展：

```text
Travel Planning Workflow
Weekly Review Workflow
Research Briefing Workflow
Email Triage Workflow
```

---

## 15.2 Handoff 工具

```python
from langchain.messages import AIMessage, ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command


@tool
def transfer_to_briefing(
    request: str,
    runtime: ToolRuntime,
) -> Command:
    """Transfer the current request to the briefing workflow."""

    last_ai_message = next(
        message
        for message in reversed(runtime.state["messages"])
        if isinstance(message, AIMessage)
    )

    transfer_message = ToolMessage(
        content=f"Transferred briefing request: {request}",
        tool_call_id=runtime.tool_call_id,
    )

    return Command(
        goto="briefing_workflow",
        update={
            "active_agent": "briefing_workflow",
            "messages": [
                last_ai_message,
                transfer_message,
            ],
        },
        graph=Command.PARENT,
    )
```

Handoff 必须保证：

* Tool Call 和 Tool Message 成对出现；
* 下一个节点能够读取请求上下文；
* 不把不需要的私有状态泄露给子 Agent；
* 记录 Handoff 审计日志。

---

# 16. Structured Output

需要结构稳定的 Agent 输出时，应使用 Pydantic Schema。

## 16.1 ScheduleProposal

```python
class ProposedEvent(BaseModel):
    title: str
    start_at: datetime
    end_at: datetime
    timezone: str
    reason: str
    score: float


class ScheduleProposal(BaseModel):
    summary: str
    events: list[ProposedEvent]
    warnings: list[str]
    requires_approval: bool
```

---

## 16.2 BriefingDraft

```python
class BriefingSectionDraft(BaseModel):
    title: str
    content: str
    source_ids: list[str]
    warnings: list[str]


class BriefingDraft(BaseModel):
    title: str
    summary: str
    sections: list[BriefingSectionDraft]
    action_items: list[str]
```

---

# 17. Agent Tool 设计

每个 Tool 必须满足：

* 输入使用 Pydantic Schema；
* 输出使用可序列化结构；
* 不返回 Django ORM 对象；
* 不包含复杂业务逻辑；
* 不绕过权限检查；
* 不直接调用 ORM；
* 必须调用 Application Service；
* 写入 Tool 必须支持幂等；
* 高风险 Tool 必须能够被 HITL 中断。

---

## 17.1 查询类工具

```text
get_current_datetime
get_user_preferences

list_events
get_event
detect_conflicts
find_free_slots

list_tasks
get_task
list_reminders
```

---

## 17.2 写入类工具

```text
create_event
update_event
cancel_event

create_task
update_task
complete_task

create_reminder
cancel_reminder
```

---

## 17.3 规划类工具

```text
build_schedule_proposal
score_time_slots
estimate_plan_capacity
validate_schedule_proposal
```

---

## 17.4 转交类工具

```text
transfer_to_briefing
```

---

## 17.5 Tool 示例

```python
class CreateEventInput(BaseModel):
    title: str
    start_at: datetime
    end_at: datetime
    timezone: str

    description: str = ""
    location: str = ""

    idempotency_key: str


def create_event_tool(
    input_data: CreateEventInput,
    context: ToolContext,
) -> dict:
    event = event_service.create_event(
        CreateEventCommand(
            user_id=context.user_id,
            title=input_data.title,
            start_at=input_data.start_at,
            end_at=input_data.end_at,
            timezone=input_data.timezone,
            description=input_data.description,
            location=input_data.location,
            idempotency_key=input_data.idempotency_key,
        )
    )

    return {
        "success": True,
        "event": {
            "id": str(event.id),
            "title": event.title,
            "start_at": event.start_at.isoformat(),
            "end_at": event.end_at.isoformat(),
        },
    }
```

---

# 18. 风险与审批策略

## 18.1 低风险操作

可直接执行：

* 查询日程；
* 查询任务；
* 查询提醒；
* 查询天气；
* 查询新闻；
* 生成简报；
* 搜索空闲时间；
* 生成计划建议；
* 检测冲突。

---

## 18.2 中风险操作

默认可以执行，但执行后必须告知用户：

* 创建个人任务；
* 标记任务完成；
* 创建普通提醒；
* 修改简报偏好；
* 创建不占用日历时间的草稿计划。

---

## 18.3 高风险操作

必须审批：

* 创建正式日程；
* 修改日程时间；
* 删除或取消日程；
* 修改重复日程；
* 批量创建事务；
* 自动重排多个任务；
* 邀请其他参与人；
* 修改外部日历；
* 向他人发送消息；
* 删除任务和提醒；
* 修改多个未来实例。

---

## 18.4 审批信息

审批界面必须展示：

```text
操作类型
对象名称
当前时间
拟修改后的时间
影响范围
是否重复
提醒设置
冲突信息
参与人
```

---

# 19. 核心领域模型

## 19.1 UserPreference

```text
UserPreference
├── user
├── timezone
├── locale
├── workday_start
├── workday_end
├── sleep_start
├── sleep_end
├── default_event_duration_minutes
├── preferred_focus_periods
├── default_reminder_offsets
├── weather_location
├── news_topics
├── briefing_time
└── planning_rules
```

稳定偏好优先保存为结构化数据，而不是只写入 Agent Memory。

---

## 19.2 CalendarEvent

```text
CalendarEvent
├── id
├── user
├── title
├── description
├── start_at
├── end_at
├── timezone
├── location
├── status
├── visibility
├── recurrence_rule
├── source
├── external_id
├── created_by
├── version
├── created_at
└── updated_at
```

规则：

* `start_at` 和 `end_at` 使用 UTC 保存；
* `timezone` 保存原始 IANA 时区；
* `end_at` 必须晚于 `start_at`；
* 允许重叠，但必须检测冲突；
* 外部事件保存 `source` 和 `external_id`；
* 修改事件使用乐观锁或版本号。

---

## 19.3 Task

```text
Task
├── id
├── user
├── project
├── parent_task
├── title
├── description
├── status
├── priority
├── due_at
├── estimated_minutes
├── planned_start_at
├── planned_end_at
├── actual_started_at
├── completed_at
├── source
├── tags
├── created_at
└── updated_at
```

必须区分：

```text
due_at
```

表示最迟完成时间。

```text
planned_start_at / planned_end_at
```

表示计划执行时间。

```text
estimated_minutes
```

表示预计工作量。

---

## 19.4 Reminder

```text
Reminder
├── id
├── user
├── target_type
├── target_id
├── title
├── trigger_at
├── timezone
├── channel
├── status
├── deduplication_key
├── queued_at
├── sent_at
├── retry_count
├── failure_reason
├── created_at
└── updated_at
```

状态：

```text
pending
queued
sending
sent
failed
cancelled
```

---

## 19.5 BriefingDefinition

```text
BriefingDefinition
├── id
├── user
├── name
├── enabled
├── schedule_type
├── schedule_expression
├── timezone
├── sections
├── delivery_channels
├── prompt_template
├── next_run_at
├── last_run_at
├── created_at
└── updated_at
```

---

## 19.6 BriefingRun

```text
BriefingRun
├── id
├── definition
├── scheduled_for
├── started_at
├── finished_at
├── status
├── collected_data
├── rendered_content
├── delivery_results
├── error
└── idempotency_key
```

---

## 19.7 ActionProposal

```text
ActionProposal
├── id
├── user
├── conversation
├── agent_run_id
├── original_request
├── action_type
├── action_payload
├── risk_level
├── status
├── requires_approval
├── approved_at
├── executed_at
├── execution_result
├── error
└── idempotency_key
```

状态：

```text
proposed
awaiting_approval
approved
rejected
executing
executed
failed
expired
```

---

# 20. Application Service 设计

## 20.1 EventService

```python
class EventService:
    def create_event(
        self,
        command: CreateEventCommand,
    ) -> CalendarEvent:
        ...

    def update_event(
        self,
        command: UpdateEventCommand,
    ) -> CalendarEvent:
        ...

    def cancel_event(
        self,
        event_id: UUID,
        user_id: UUID,
    ) -> None:
        ...

    def list_events(
        self,
        query: EventQuery,
    ) -> list[CalendarEvent]:
        ...

    def detect_conflicts(
        self,
        user_id: UUID,
        start_at: datetime,
        end_at: datetime,
        exclude_event_id: UUID | None = None,
    ) -> list[CalendarEvent]:
        ...
```

---

## 20.2 TaskService

```python
class TaskService:
    def create_task(
        self,
        command: CreateTaskCommand,
    ) -> Task:
        ...

    def update_task(
        self,
        command: UpdateTaskCommand,
    ) -> Task:
        ...

    def complete_task(
        self,
        task_id: UUID,
        user_id: UUID,
    ) -> Task:
        ...

    def list_tasks(
        self,
        query: TaskQuery,
    ) -> list[Task]:
        ...

    def reschedule_task(
        self,
        task_id: UUID,
        planned_start_at: datetime,
        planned_end_at: datetime,
    ) -> Task:
        ...
```

---

## 20.3 ReminderService

```python
class ReminderService:
    def create_reminder(
        self,
        command: CreateReminderCommand,
    ) -> Reminder:
        ...

    def cancel_reminder(
        self,
        reminder_id: UUID,
        user_id: UUID,
    ) -> None:
        ...

    def dispatch_due_reminders(
        self,
        now: datetime,
        batch_size: int = 100,
    ) -> int:
        ...

    def send_reminder(
        self,
        reminder_id: UUID,
    ) -> None:
        ...
```

---

## 20.4 PlanningService

```python
class PlanningService:
    def find_free_slots(
        self,
        user_id: UUID,
        range_start: datetime,
        range_end: datetime,
        duration_minutes: int,
        constraints: PlanningConstraints,
    ) -> list[TimeSlot]:
        ...

    def score_slots(
        self,
        slots: list[TimeSlot],
        preferences: UserPreference,
    ) -> list[ScoredTimeSlot]:
        ...

    def build_schedule_proposal(
        self,
        request: ScheduleRequest,
    ) -> ScheduleProposal:
        ...

    def validate_schedule_proposal(
        self,
        proposal: ScheduleProposal,
    ) -> ProposalValidationResult:
        ...
```

---

## 20.5 BriefingService

```python
class BriefingService:
    def generate(
        self,
        definition_id: UUID,
        scheduled_for: datetime,
    ) -> BriefingRun:
        ...

    def collect_sections(
        self,
        definition: BriefingDefinition,
    ) -> list[BriefingSectionResult]:
        ...

    def render(
        self,
        definition: BriefingDefinition,
        sections: list[BriefingSectionResult],
    ) -> BriefingDraft:
        ...

    def deliver(
        self,
        run: BriefingRun,
    ) -> list[DeliveryResult]:
        ...
```

---

# 21. 时间处理规范

## 21.1 数据库统一保存 UTC

所有时间字段使用 UTC 保存。

展示时转换为用户时区。

---

## 21.2 时区使用 IANA 名称

使用：

```text
Asia/Singapore
Asia/Shanghai
America/Los_Angeles
Europe/London
```

禁止只保存：

```text
UTC+8
```

---

## 21.3 相对时间必须注入基准

解析：

```text
明天下午三点
下周一
三小时后
月底前
```

必须提供：

```text
current_datetime
user_timezone
locale
```

---

## 21.4 LLM 时间结果必须确定性校验

LLM 可以提出时间解析结果，但必须经过：

* 日期合法性检查；
* 时区转换；
* 开始时间和结束时间检查；
* 当前时间检查；
* 模糊字段检查。

---

## 21.5 模糊时间保留不确定性

例如：

```text
明天晚上提醒我
```

可以解析为：

```json
{
  "resolved": false,
  "date": "2026-07-16",
  "time_range": [
    "18:00",
    "21:00"
  ],
  "missing_fields": [
    "exact_time"
  ],
  "confidence": 0.58
}
```

Agent 可以：

* 使用明确的用户默认偏好；
* 或向用户询问具体时间。

---

# 22. 提醒调度架构

不建议为每个 Reminder 动态创建一条 Celery Beat 配置。

建议使用统一扫描器：

```text
Celery Beat 每 30 秒触发
        ↓
dispatch_due_reminders
        ↓
查询 trigger_at <= now
且 status = pending
        ↓
select_for_update(skip_locked)
        ↓
标记 queued
        ↓
投递 send_reminder
        ↓
通知渠道发送
        ↓
标记 sent 或 failed
```

伪代码：

```python
@shared_task
def dispatch_due_reminders() -> int:
    with transaction.atomic():
        reminders = (
            Reminder.objects
            .select_for_update(skip_locked=True)
            .filter(
                status=ReminderStatus.PENDING,
                trigger_at__lte=timezone.now(),
            )
            .order_by("trigger_at")[:100]
        )

        ids = [
            reminder.id
            for reminder in reminders
        ]

        Reminder.objects.filter(
            id__in=ids
        ).update(
            status=ReminderStatus.QUEUED,
            queued_at=timezone.now(),
        )

    for reminder_id in ids:
        send_reminder.delay(
            str(reminder_id)
        )

    return len(ids)
```

发送任务必须幂等。

---

# 23. 简报插件架构

所有 Briefing Section 实现统一接口。

```python
class BriefingSection(Protocol):
    type_name: str

    def collect(
        self,
        context: BriefingContext,
        config: dict,
    ) -> BriefingSectionResult:
        ...
```

结果结构：

```python
class BriefingSectionResult(BaseModel):
    type: str
    title: str
    status: str

    data: dict
    source_items: list[dict]
    warnings: list[str] = []
```

注册中心：

```python
SECTION_REGISTRY = {
    "calendar": CalendarSection(),
    "tasks": TaskSection(),
    "weather": WeatherSection(),
    "news": NewsSection(),
}
```

后续可以扩展：

```text
github
email
server_health
mmkb
finance
research_papers
```

新增 Section 时只需要：

1. 实现 Section；
2. 注册到 Registry；
3. 定义配置 Schema；
4. 增加测试。

---

# 24. 简报执行流程

```text
调度器发现 BriefingDefinition 到期
        ↓
创建 BriefingRun
        ↓
并行收集 Section 数据
        ↓
标准化数据
        ↓
来源去重
        ↓
时间和可信度排序
        ↓
Briefing Editor Agent 生成草稿
        ↓
确定性校验来源和时间
        ↓
保存 rendered_content
        ↓
发送到通知渠道
        ↓
保存发送结果
```

必须保存原始结构化数据，不能只保存最终文字。

---

# 25. Provider 接口

## 25.1 WeatherProvider

```python
class WeatherProvider(Protocol):
    def forecast(
        self,
        location: str,
        start_date: date,
        days: int,
    ) -> WeatherForecast:
        ...
```

---

## 25.2 NewsProvider

```python
class NewsProvider(Protocol):
    def search(
        self,
        topics: list[str],
        start_at: datetime,
        end_at: datetime,
        limit: int,
    ) -> list[NewsItem]:
        ...
```

---

## 25.3 CalendarProvider

```python
class CalendarProvider(Protocol):
    def list_events(
        self,
        start_at: datetime,
        end_at: datetime,
    ) -> list[ExternalEvent]:
        ...

    def create_event(
        self,
        event: ExternalEventCreate,
    ) -> ExternalEvent:
        ...

    def update_event(
        self,
        external_id: str,
        event: ExternalEventUpdate,
    ) -> ExternalEvent:
        ...
```

---

## 25.4 NotificationProvider

```python
class NotificationProvider(Protocol):
    def send(
        self,
        recipient: str,
        title: str,
        content: str,
        idempotency_key: str,
    ) -> DeliveryResult:
        ...
```

第一版先实现：

```text
ConsoleNotificationProvider
```

然后接入：

```text
EmailNotificationProvider
TelegramNotificationProvider
```

---

# 26. API 设计

## 26.1 Chat API

```text
POST /api/v1/chat/messages
```

请求：

```json
{
  "conversation_id": "uuid",
  "message": "明天下午三点提醒我提交报告"
}
```

SSE 事件：

```text
message.started
agent.started
agent.plan_updated
tool.started
tool.completed
handoff.started
approval.required
approval.received
message.delta
message.completed
```

---

## 26.2 日程 API

```text
GET    /api/v1/events
POST   /api/v1/events
GET    /api/v1/events/{id}
PATCH  /api/v1/events/{id}
DELETE /api/v1/events/{id}
```

---

## 26.3 任务 API

```text
GET    /api/v1/tasks
POST   /api/v1/tasks
GET    /api/v1/tasks/{id}
PATCH  /api/v1/tasks/{id}
POST   /api/v1/tasks/{id}/complete
```

---

## 26.4 提醒 API

```text
GET    /api/v1/reminders
POST   /api/v1/reminders
PATCH  /api/v1/reminders/{id}
DELETE /api/v1/reminders/{id}
```

---

## 26.5 规划 API

```text
POST /api/v1/planning/free-slots
POST /api/v1/planning/proposals
```

---

## 26.6 审批 API

```text
POST /api/v1/action-proposals/{id}/approve
POST /api/v1/action-proposals/{id}/edit
POST /api/v1/action-proposals/{id}/reject
```

---

## 26.7 简报 API

```text
GET    /api/v1/briefings
POST   /api/v1/briefings
GET    /api/v1/briefings/{id}
PATCH  /api/v1/briefings/{id}
POST   /api/v1/briefings/{id}/run

GET    /api/v1/briefing-runs
GET    /api/v1/briefing-runs/{id}
```

---

# 27. 代码仓库结构

```text
time-agent/
├── README.md
├── PROJECT_SPEC.md
├── AGENTS.md
├── TODO.md
├── docker-compose.yml
├── .env.example
├── pyproject.toml
├── uv.lock
├── manage.py
│
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   ├── test.py
│   │   └── production.py
│   ├── urls.py
│   ├── celery.py
│   ├── asgi.py
│   └── wsgi.py
│
├── apps/
│   ├── accounts/
│   │   ├── models.py
│   │   ├── services.py
│   │   └── api/
│   │
│   ├── events/
│   │   ├── models.py
│   │   ├── selectors.py
│   │   ├── services.py
│   │   ├── validators.py
│   │   └── api/
│   │
│   ├── tasks/
│   │   ├── models.py
│   │   ├── selectors.py
│   │   ├── services.py
│   │   ├── validators.py
│   │   └── api/
│   │
│   ├── reminders/
│   │   ├── models.py
│   │   ├── selectors.py
│   │   ├── services.py
│   │   ├── scheduler.py
│   │   ├── delivery.py
│   │   └── celery_tasks.py
│   │
│   ├── planning/
│   │   ├── free_slots.py
│   │   ├── conflict_detection.py
│   │   ├── scoring.py
│   │   └── schemas.py
│   │
│   ├── briefings/
│   │   ├── models.py
│   │   ├── engine.py
│   │   ├── registry.py
│   │   ├── schemas.py
│   │   ├── graph.py
│   │   ├── celery_tasks.py
│   │   └── sections/
│   │       ├── base.py
│   │       ├── calendar.py
│   │       ├── tasks.py
│   │       ├── weather.py
│   │       └── news.py
│   │
│   ├── integrations/
│   │   ├── weather/
│   │   │   ├── base.py
│   │   │   ├── open_meteo.py
│   │   │   └── mock.py
│   │   ├── news/
│   │   │   ├── base.py
│   │   │   ├── rss.py
│   │   │   └── mock.py
│   │   ├── calendar/
│   │   │   ├── base.py
│   │   │   ├── google.py
│   │   │   └── caldav.py
│   │   └── notifications/
│   │       ├── base.py
│   │       ├── email.py
│   │       ├── telegram.py
│   │       └── console.py
│   │
│   ├── agents/
│   │   ├── outer_graph.py
│   │   ├── state.py
│   │   ├── context.py
│   │   ├── routing.py
│   │   ├── policies.py
│   │   ├── prompts/
│   │   │   ├── time_steward.md
│   │   │   ├── briefing_editor.md
│   │   │   └── news_research.md
│   │   ├── middleware/
│   │   │   ├── runtime_context.py
│   │   │   ├── tool_policy.py
│   │   │   ├── audit.py
│   │   │   └── memory_policy.py
│   │   ├── agents/
│   │   │   ├── time_steward.py
│   │   │   ├── briefing_editor.py
│   │   │   └── news_research.py
│   │   ├── tools/
│   │   │   ├── event_tools.py
│   │   │   ├── task_tools.py
│   │   │   ├── reminder_tools.py
│   │   │   ├── planning_tools.py
│   │   │   ├── briefing_tools.py
│   │   │   └── handoff_tools.py
│   │   └── memory/
│   │       ├── checkpointer.py
│   │       ├── store.py
│   │       └── schemas.py
│   │
│   ├── conversations/
│   │   ├── models.py
│   │   ├── services.py
│   │   └── api/
│   │
│   └── audit/
│       ├── models.py
│       └── services.py
│
├── common/
│   ├── exceptions.py
│   ├── time.py
│   ├── idempotency.py
│   ├── logging.py
│   └── types.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── agents/
│   ├── middleware/
│   ├── workflows/
│   └── fixtures/
│
└── docs/
    ├── architecture.md
    ├── api.md
    ├── domain-model.md
    ├── agent-system.md
    ├── memory.md
    └── decisions/
        ├── 0001-service-layer.md
        ├── 0002-reminder-scheduling.md
        ├── 0003-agent-approval.md
        ├── 0004-agent-as-node.md
        └── 0005-memory-boundaries.md
```

---

# 28. 监控指标

至少暴露以下指标。

```text
time_agent_agent_runs_total
time_agent_agent_failures_total
time_agent_agent_run_seconds

time_agent_model_calls_total
time_agent_model_failures_total
time_agent_model_tokens_total

time_agent_tool_calls_total
time_agent_tool_failures_total
time_agent_tool_call_seconds

time_agent_handoffs_total
time_agent_agent_limit_reached_total

time_agent_reminders_pending
time_agent_reminders_sent_total
time_agent_reminders_failed_total
time_agent_reminder_delivery_seconds

time_agent_briefing_runs_total
time_agent_briefing_failures_total
time_agent_briefing_generation_seconds

time_agent_action_proposals_total
time_agent_action_approvals_total
time_agent_action_rejections_total

time_agent_provider_requests_total
time_agent_provider_failures_total
time_agent_provider_request_seconds
```

日志至少包含：

```text
request_id
user_id
conversation_id
thread_id
agent_run_id
active_agent
model_call_id
tool_call_id
action_proposal_id
briefing_run_id
reminder_id
provider
duration_ms
status
error_code
```

---

# 29. 测试策略

## 29.1 单元测试

测试：

* UTC 和用户时区转换；
* 夏令时；
* 跨天日程；
* 冲突检测；
* 空闲时间计算；
* 候选时间评分；
* Reminder 幂等；
* Task 状态转换；
* Provider Mock；
* Briefing Registry；
* Tool Schema；
* Risk Policy；
* Dynamic Tool Policy。

---

## 29.2 Agent 测试

建立固定测试集：

```text
明天下午三点提醒我提交报告
今天有什么安排
下周一上午十点开会
这周找两个晚上安排健身
把明天下午的会议推迟一个小时
取消我周五的会议
生成今天的晨报
每天早上八点给我生成晨报
```

每个案例检查：

* Agent 是否调用正确工具；
* 是否使用了用户时区；
* 是否读取了必要数据；
* 是否触发了审批；
* 是否发生错误写入；
* 是否正确 Handoff；
* 是否输出明确时间；
* 是否陷入重复循环。

---

## 29.3 Middleware 测试

测试：

* 模型调用限制；
* 工具调用限制；
* Tool Retry；
* Model Retry；
* Fallback；
* Summarization；
* HITL Interrupt；
* Dynamic Tool Policy；
* Memory Write Policy；
* Audit Log。

---

## 29.4 Workflow 测试

测试：

* 用户请求进入主 Agent；
* 主 Agent 转交简报；
* 定时简报绕过主 Agent；
* Reminder 进入确定性 Dispatcher；
* Calendar Webhook 进入 Sync Workflow；
* Briefing Section 并行收集；
* Briefing Agent 输出结构化结果。

---

## 29.5 时间测试冻结当前时间

测试中禁止依赖真实系统时间。

统一使用固定时间：

```text
2026-07-15T10:00:00+08:00
```

---

# 30. 环境变量

```text
DJANGO_SETTINGS_MODULE=
DJANGO_SECRET_KEY=
DJANGO_DEBUG=

DATABASE_URL=
REDIS_URL=

CELERY_BROKER_URL=
CELERY_RESULT_BACKEND=

DEFAULT_TIMEZONE=
DEFAULT_LOCALE=

LLM_PROVIDER=
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
LLM_FALLBACK_MODEL=
LLM_SUMMARY_MODEL=

LANGGRAPH_CHECKPOINTER_URL=
LANGGRAPH_STORE_URL=

AGENT_MODEL_CALL_LIMIT=
AGENT_TOOL_CALL_LIMIT=

WEATHER_PROVIDER=
WEATHER_API_KEY=

NEWS_PROVIDER=

EMAIL_HOST=
EMAIL_PORT=
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
EMAIL_FROM_ADDRESS=

TELEGRAM_BOT_TOKEN=

LOG_LEVEL=
PROMETHEUS_ENABLED=
```

---

# 31. 开发阶段

## 阶段 0：仓库骨架

完成：

* Django；
* PostgreSQL；
* Redis；
* Celery；
* Docker Compose；
* 健康检查；
* JSON 日志；
* 基础测试环境。

---

## 阶段 1：事务领域核心

完成：

* UserPreference；
* CalendarEvent；
* Task；
* Reminder；
* Service Layer；
* 时间工具；
* 冲突检测；
* 空闲时间搜索。

此阶段不接 Agent。

---

## 阶段 2：提醒系统

完成：

* Reminder Dispatcher；
* Console Notification；
* 幂等；
* 失败重试；
* 发送状态；
* Prometheus 指标。

---

## 阶段 3：LangGraph 基础设施

完成：

* AppState；
* RuntimeContext；
* PostgreSQL Checkpointer；
* PostgreSQL Store；
* Trigger Envelope；
* Outer Graph；
* Trigger Router。

---

## 阶段 4：Time Steward Agent

完成：

* `create_agent()`；
* 查询工具；
* 任务工具；
* 提醒工具；
* 规划工具；
* Middleware；
* Agent 测试；
* 流式事件。

---

## 阶段 5：HITL 和 ActionProposal

完成：

* ActionProposal；
* Risk Policy；
* HumanInTheLoopMiddleware；
* Interrupt；
* 恢复执行；
* 审批 API；
* 编辑后执行。

---

## 阶段 6：Briefing Workflow

完成：

* BriefingDefinition；
* BriefingRun；
* Briefing Registry；
* Calendar Section；
* Task Section；
* Briefing Editor Agent；
* Handoff；
* 手动运行简报。

---

## 阶段 7：天气和新闻

完成：

* WeatherProvider；
* Weather Section；
* RSS NewsProvider；
* News Section；
* News Research Agent；
* 新闻去重；
* 来源保存；
* 简报时间校验。

---

## 阶段 8：定时简报

完成：

* Celery Beat；
* Trigger Envelope；
* 定时直接进入 Briefing Workflow；
* 自动保存；
* 自动发送；
* 失败重试。

---

## 阶段 9：外部集成

按顺序接入：

1. 邮件通知；
2. Telegram；
3. Google Calendar；
4. CalDAV；
5. GitHub；
6. Gmail；
7. MMKB；
8. 系统监控简报。

---

## 阶段 10：高级规划

最后实现：

* 长期目标拆解；
* 时间块规划；
* 多任务排序；
* 延期任务重排；
* 周计划；
* 周复盘；
* 基于历史数据调整预计时间；
* 根据天气建议调整活动。

---

# 32. Vibe Coding 约束

## 32.1 一次只完成一个边界明确的任务

推荐：

```text
实现 CalendarEvent 模型、迁移和模型测试。
不要实现 API、Agent Tool 或外部日历同步。
```

禁止：

```text
把整个时间管理 Agent 做完。
```

---

## 32.2 每个任务声明允许修改的目录

例如：

```text
允许修改：
apps/events/
tests/unit/events/

禁止修改：
apps/agents/
apps/briefings/
config/settings/
```

---

## 32.3 开发顺序

```text
Model
  ↓
Service
  ↓
Unit Test
  ↓
API
  ↓
Agent Tool
  ↓
Agent
  ↓
Outer Graph
```

---

## 32.4 Agent Tool 不包含业务规则

Tool 只负责：

* 参数接收；
* 调用 Service；
* 返回结构化结果。

复杂业务逻辑必须在 Service Layer。

---

## 32.5 Prompt 不包含关键业务规则

Prompt 不能承担：

* 权限判断；
* 冲突判断；
* 提醒幂等；
* 时间合法性；
* Task 状态转换；
* Action 风险判断。

---

## 32.6 不允许无限 Agent 循环

必须配置：

* Model Call Limit；
* Tool Call Limit；
* Tool Retry Limit；
* Model Retry Limit；
* 超限退出逻辑。

---

## 32.7 新 Agent 必须有拆分理由

新增 Agent 时必须记录 ADR，说明：

* 为什么不能作为现有 Agent 的 Tool；
* 为什么不能作为普通 Workflow Node；
* 它需要哪些独立上下文；
* 它需要哪些工具；
* 它的持久化策略是什么；
* 它的输出 Schema 是什么。

---

## 32.8 Memory 写入必须受控

AI 不得随意把用户对话全部写入长期 Memory。

必须经过：

* Memory Policy；
* 数据分类；
* 敏感信息检查；
* 去重；
* 用户覆盖机制。

---

## 32.9 每次修改后执行

```text
格式化
静态检查
单元测试
相关集成测试
Agent 测试
Django system check
迁移检查
```

---

# 33. AGENTS.md 建议内容

```text
1. PostgreSQL 是业务事实来源。
2. Agent Tool 不得直接调用 Django ORM。
3. 所有写操作必须经过 Application Service。
4. 所有时间在数据库中以 UTC 保存。
5. 所有用户时间必须结合 IANA 时区解析。
6. Time Steward Agent 使用 create_agent 创建。
7. 外层 StateGraph 只负责触发路由、Handoff 和工作流编排。
8. 不得把 Agent 内部循环重复拆成大量外层节点。
9. 定时简报必须直接进入 Briefing Workflow。
10. 高风险操作必须使用 ActionProposal 和 HITL。
11. 提醒和简报任务必须实现幂等。
12. 外部 API 必须通过 Provider 接口调用。
13. 新增 Briefing Section 必须通过 Registry 注册。
14. 不得在 Prompt 中实现业务规则。
15. Agent 必须设置模型和工具调用限制。
16. Agent Memory 不能替代 Domain Database。
17. 长期 Memory 写入必须通过 Memory Policy。
18. 新增 Agent 必须提供明确的拆分理由。
19. 每个新 Service 必须包含单元测试。
20. 不得记录 Token、API Key 或用户敏感信息。
21. 未明确要求时，不得修改任务范围之外的文件。
22. 第一版禁止提前引入大规模多 Agent 系统。
```

---

# 34. 推荐的前 16 个开发任务

## Task 01

初始化 Django、PostgreSQL、Redis、Celery 和 Docker Compose。

## Task 02

实现 UserPreference 模型和时间工具。

## Task 03

实现 CalendarEvent 模型、校验和测试。

## Task 04

实现 Task 模型、状态转换和测试。

## Task 05

实现 Reminder 模型、幂等键和测试。

## Task 06

实现 EventService、TaskService 和 ReminderService。

## Task 07

实现冲突检测和空闲时间搜索。

## Task 08

实现 Reminder Dispatcher 和 Console Notification Provider。

## Task 09

实现 Event、Task 和 Reminder REST API。

## Task 10

实现 TriggerEnvelope、RuntimeContext 和 AppState。

## Task 11

接入 PostgreSQL Checkpointer 和 Store。

## Task 12

实现 Outer Graph 和确定性 Trigger Router。

## Task 13

实现 Time Steward Agent 的只读工具。

## Task 14

接入 Agent Middleware 和调用限制。

## Task 15

实现写入 Tool、ActionProposal 和 HITL。

## Task 16

实现 Briefing Workflow 和 Handoff。

完成以上任务后，再接入天气和新闻。

---

# 35. 第一个可演示版本

第一个 Demo：

```text
用户：
明天下午三点提醒我提交项目报告。

Time Steward Agent：
调用当前时间工具。
调用时间解析逻辑。
调用创建提醒 Tool。

系统：
创建 Reminder 数据库记录。

Celery：
在到期时间发送通知。
```

第二个 Demo：

```text
用户：
这周帮我安排两次健身。

Time Steward Agent：
查询日程。
查询偏好。
搜索空闲时间。
生成候选计划。
检查冲突。
向用户展示 ActionProposal。
等待用户确认。
写入正式日程。
```

第三个 Demo：

```text
用户：
生成今天的晨报。

Time Steward Agent：
调用 transfer_to_briefing。

Briefing Workflow：
读取日程。
读取任务。
获取天气。
收集新闻。
调用 Briefing Editor Agent。
返回简报。
```

第四个 Demo：

```text
Celery Beat：
每天 08:00 触发 scheduled_briefing。

Outer Graph：
直接路由到 Briefing Workflow。

Briefing Workflow：
生成、保存并发送简报。
```

---

# 36. MVP 验收标准

## 可靠性

* 提醒不依赖 Agent 进程常驻；
* 相同提醒不会重复发送；
* Celery 重试不会产生重复结果；
* 所有时间能够追溯到明确时区；
* Provider 失败不会导致整份简报丢失；
* Agent 超限后能够安全退出。

---

## Agent 安全

* 高风险写操作不会直接执行；
* 用户可以看到具体变更；
* 用户拒绝后不会修改数据；
* Tool 参数经过 Schema 校验；
* Tool 不直接操作 ORM；
* Agent 不能绕过 Application Service；
* 长期 Memory 写入受策略控制。

---

## Agent 架构

* Time Steward Agent 使用 `create_agent()`；
* Middleware 可独立测试；
* 外层 Graph 保持轻量；
* 用户简报请求可以 Handoff；
* 定时简报直接进入 Briefing Workflow；
* Reminder 不经过 LLM；
* Agent 和 Workflow 具有清楚边界。

---

## 可扩展性

* 新增 Briefing Section 不修改核心引擎；
* 新增 Provider 不修改业务服务；
* 更换模型不影响领域模型；
* 新 Agent 可以通过 Handoff 接入；
* 新触发类型可以通过 Outer Graph 路由；
* 后续可以接入外部日历。

---

## 可观察性

* 每次 Agent Run 有唯一 ID；
* 每次 Model Call 有记录；
* 每次 Tool Call 有记录；
* 每次 Handoff 有记录；
* 每次 Reminder 有状态记录；
* 每次 BriefingRun 保存原始数据和最终结果；
* 关键流程具有 Prometheus 指标。

---

# 37. 最终职责边界

```text
PostgreSQL
负责保存业务事实

Celery
负责准时触发和异步执行

Application Service
负责业务规则

Provider
负责访问外部系统

Agent Tool
负责向 Agent 暴露能力

create_agent
负责 Agent 内部模型—工具循环

Middleware
负责上下文、限制、审批和审计

Outer StateGraph
负责触发路由、Handoff 和工作流拓扑

Checkpointer
负责当前 Thread 的执行状态

Store
负责跨 Thread 的长期软性记忆

LLM
负责理解、规划、修订和表达

用户审批
负责批准高风险操作
```

无论后续加入天气、新闻、邮件、GitHub、知识库、旅行规划还是系统监控，都不应破坏以上边界。
