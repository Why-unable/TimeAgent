# 三十、进一步优化 Tool Architecture，而不是只优化 Planner

除了 Planning Harness，本轮还需要重新审计 Time Steward 当前完整 Tool 集合。

当前注册工具数量较多。

不要预设：

> 工具越少越好。

也不要预设：

> 一个业务操作就应该对应一个独立 Tool。

真正需要研究的是：

> **当前 Tool 集合是否为 LLM 提供了清晰、低歧义、可组合、低成本的 Action Space。**

本轮请从 Agent Harness 视角重新设计 Tool Architecture。

---

# 三十一、区分三个不同概念

必须明确区分：

## 1. Tool Registry

系统总共具备哪些底层能力。

例如：

```text
Task
Calendar
Reminder
Planning
Memory
Insight
Decision
Integration
Briefing
```

这是系统 Capability。

---

## 2. Tool Surface

某一次 Agent Reasoning 时：

> 模型实际能看到哪些 Tool？

例如用户说：

```text
“帮我安排下周任务”
```

模型可能只需要看到：

```text
get_planning_context
propose_schedule_plan
edit_schedule_plan
validate_schedule_plan
apply_schedule_plan
get_capacity_forecast
recommend_task_duration
```

而不是全部几十个工具。

---

## 3. Tool Interaction Cost

为了完成一个用户目标：

```text
需要几次 Tool Call？
需要多少参数？
Tool Result 多大？
是否重复查询？
是否产生无意义往返？
```

最终优化的重点应该是：

```text
Capability Coverage
        +
Tool Selection Accuracy
        +
Tool Call Efficiency
        +
Low Ambiguity
```

而不是单纯追求 Tool Count 最小。

---

# 三十二、对当前所有 Tool 做一次系统审计

为所有注册 Tool 建立表格：

| Tool | Domain | Read/Write | 用户意图 | 是否高频 | 与其他 Tool 重叠 | 参数复杂度 | 输出大小 | 是否适合保留 |
| ---- | ------ | ---------- | ---- | ---- | ----------- | ----- | ---- | ------ |

然后分类：

```text
A. Essential Primitive
B. Composite Workflow Tool
C. Redundant / Overlapping
D. Too Fine-grained
E. Too Coarse-grained
F. Rare / Specialist
G. Internal-only Candidate
```

---

# 三十三、重点寻找“语义重复”的 Tool

例如检查：

```text
list_x
get_x

update_x
change_x
complete_x
cancel_x

plan
compare
validate
edit
regenerate
lock
apply
```

不要因为名字不同就认为一定需要独立 Tool。

对于每一组问：

```text
LLM 是否容易理解它们的差异？

用户请求是否经常导致模型在几个工具之间犹豫？

两个 Tool 是否只是同一 Resource 的不同 operation？

合并以后 Schema 是否反而会更复杂？

拆开以后是否能明显提高 Policy / HITL / 可观测性？
```

---

# 三十四、研究 Resource-oriented Tool Design

例如 Task 当前可能存在多个写工具。

研究是否存在合理的：

```text
mutate_tasks
```

形式：

```json
{
  "operations": [
    {
      "action": "update",
      "task_id": "...",
      "changes": {}
    }
  ]
}
```

类似 Calendar 的 mutation model。

但不要默认一定要合并。

比较：

```text
方案 A
create_task
update_task
complete_task
cancel_task
reschedule_task

方案 B
mutate_tasks

方案 C
保留高风险操作独立，
低风险操作适度合并
```

评估：

```text
Tool Selection Accuracy
Schema Complexity
HITL Policy
Auditability
Idempotency
Token Cost
Error Rate
```

如果一个“大一统 Tool”导致 Schema 巨大、模型更容易填错参数，就不要合并。

---

# 三十五、优先合并“概念”，而不是机械合并函数

例如：

```text
set_schedule_plan_item_lock
```

如果本质上只是：

```text
edit_schedule_plan
```

的一种操作，就不应该为了一个字段保留独立 Agent 概念。

类似地检查：

```text
某个行为能否作为已有 Resource Tool 的 operation
```

目标是降低：

> 模型需要记住的概念数量。

而不仅仅降低 Python 函数数量。

---

# 三十六、寻找 Tool Granularity Sweet Spot

Tool 太细：

```text
Agent
→ get A
→ get B
→ get C
→ calculate
→ update A
→ update B
```

会导致：

```text
大量 Tool round trip
Token 增加
Latency 增加
中间状态复杂
```

Tool 太粗：

```text
do_everything()
```

则会导致：

```text
Agent 没有决策空间
Service 重新承担 planning
LLM 只剩触发作用
```

本轮请找：

> **Planning Primitive 与 Workflow Tool 的合理粒度。**

---

# 三十七、重点优化 Planning Tool Surface

Planning 场景尤其需要审计：

```text
get_planning_context
find_free_slots
propose_schedule_plan
compare_schedule_plans
validate_schedule_plan
edit_schedule_plan
abandon_schedule_plan
apply_schedule_plan
detect_schedule_disruptions
list_automation_policies
apply_local_replan
```

逐个回答：

```text
这个 Tool 是 Agent Decision Primitive，
还是内部 Service Primitive？

Agent 真的需要知道它吗？

是否与其他 Tool 重复？

能否通过一个更统一的 Plan Lifecycle 表达？
```

例如研究是否可以形成更清晰的：

```text
Planning Context
      ↓
Draft
      ↓
Edit / Compare
      ↓
Validate
      ↓
Apply
```

而不是让 Agent 记忆大量边缘工具。

---

# 三十八、研究 Plan Resource API

考虑让 Agent 对 SchedulePlan 形成一个稳定 mental model：

```text
SchedulePlan
```

就是一个 Resource。

围绕它提供少数清晰操作：

```text
create
edit
compare
validate
apply
abandon
```

然后：

```text
lock
move
soft preference adjustment
```

尽可能属于 edit semantics。

目标是：

> Agent 理解一个 Plan 生命周期，

而不是记住大量互相独立的 Tool 名称。

---

# 三十九、Dynamic Tool Surface 应成为 Harness 的核心能力

不要要求模型每轮看到全部工具。

根据：

```text
当前用户 Intent
当前 Agent Phase
当前 Plan State
当前权限
是否 Read-only
是否存在 ActionProposal
是否处于 Planning
是否处于 Replan
```

动态决定 Tool Surface。

例如：

```text
Planning Phase

get_planning_context
propose_schedule_plan
get_capacity_forecast
```

产生 Draft 后：

```text
Plan Review Phase

edit_schedule_plan
validate_schedule_plan
apply_schedule_plan
abandon_schedule_plan
```

进入 Replan：

```text
detect_schedule_disruptions
get_planning_context
reschedule_task
```

这比：

```text
每轮把所有 Tool 发给模型
```

更符合 Agent Harness。

---

# 四十、研究 Phase-aware Tool Exposure

目前 Tool Routing 主要从用户原始请求判断。

进一步研究：

> Tool Surface 是否应该随 Agent 当前状态变化？

例如：

```text
Initial
↓
Context Gathering

Context Ready
↓
Planning

Draft Exists
↓
Review / Repair

Valid Plan
↓
Apply
```

不同阶段暴露不同工具。

但优先利用：

```text
LangChain Middleware
Agent State
Runtime Context
Tool filtering
```

不要另写一套复杂 Agent Framework。

---

# 四十一、减少 Tool Schema Token

分析当前 Tool Definition 本身消耗多少 Context Token。

对每个 Tool 检查：

```text
名称是否清晰
description 是否过长
参数 description 是否重复
schema 是否过深
enum 是否合理
是否携带 Agent 根本不需要的字段
```

目标不是粗暴缩短说明。

而是：

> **让 Tool Schema 信息密度更高。**

例如：

```text
System Prompt
已经说明全局 timezone 规则
```

则不需要 15 个 Tool Description 都复制长篇相同规则。

公共规则应该由 Harness 统一管理。

Tool Schema 只说明自身 contract。

---

# 四十二、减少 Tool Observation Token

当前 Agent Token 高，不一定主要来自 Prompt。

统计 Tool Result：

```text
list_tasks
list_events
get_planning_context
SchedulePlan
Memory
Capacity
```

实际返回多少 Token。

检查：

```text
Agent 是否真正需要所有字段？
```

可以考虑：

```text
compact response
projection
summary fields
pagination
limit
detail level
```

例如 Planning Agent 可能只需要：

```text
task_id
title
priority
due_at
estimated_minutes
planned interval
splittable
relevant preference
```

而不是完整 Task serializer。

---

# 四十三、避免重复事实查询

如果：

```text
get_planning_context
```

已经返回：

```text
Tasks
Events
Work Hours
Free Slots
Preferences
```

那么同一轮再：

```text
list_tasks
list_events
```

通常是浪费。

研究利用：

```text
Agent State
Middleware State
Tool Observation
```

记录：

```text
本轮已经获取哪些事实
这些事实版本是否仍然有效
```

让 Agent 能复用已有 Observation。

不要做长期缓存来替代 PostgreSQL。

这里只是：

> 同一次 Agent Run 内减少重复读取。

---

# 四十四、增加 Tool Usage Metrics

对 Agent Harness 记录：

```text
Visible Tool Count

Tool Calls / Request

Unique Tool Calls

Duplicate Tool Calls

Invalid Tool Args

Blocked Tool Calls

Recovered Tool Errors

Unused Exposed Tools

Tool Result Tokens

Tool Schema Tokens
```

特别增加：

```text
Tool Utilization Ratio
```

概念上：

```text
实际调用的有效 Tool
/
本轮暴露的 Tool
```

用于判断 Tool Surface 是否太宽。

---

# 四十五、通过实验决定 Tool 合并，而不是凭直觉

对于准备合并/删除的 Tool：

建立 A/B Harness。

例如：

```text
Variant A
当前 Tool Set

Variant B
简化后的 Tool Set
```

运行同一 Regression。

比较：

```text
Task Success
Tool Selection Accuracy
Invalid Argument Rate
Model Calls
Tool Calls
Token
Latency
Planning Quality
HITL Correctness
```

只有：

```text
质量不下降
且
复杂度 / Token / Selection 明显改善
```

才保留简化方案。

---

# 四十六、允许删除 Tool，但必须说明其 Capability 去哪里了

删除一个 Agent-visible Tool 后必须属于：

```text
1. 被另一个 Tool 合并

2. 下沉到 Application Service

3. 变成 Tool 内部确定性 Primitive

4. 完全没有产品需求
```

不能：

```text
为了数字好看
直接删 Capability。
```

---

# 四十七、除了 Tool 数量，还要优化用户交互次数

用户体验不是只由 Tool 决定。

统计一个请求需要：

```text
多少次用户回答？
多少次“确认”？
多少次 approval？
多少次 Agent 自己重复解释？
```

目标：

> **只在真正改变用户取舍时询问用户。**

避免：

```text
Agent：要不要帮你排？
用户：要。

Agent：是否确认排？
用户：确认。

Agent：是否应用？
用户：应用。

HITL：是否批准？
```

这种重复确认。

---

# 四十八、Clarification Budget

建立：

```text
Clarification Budget
```

普通请求：

```text
能默认就默认
```

只有：

```text
两个高价值选项不可同时满足
且
现有事实不足以合理决定
```

时才询问。

可以考虑：

```text
max semantic clarification = 1
```

但不要硬编码成所有请求只能问一次。

真正目标是：

> 最少必要澄清。

---

# 四十九、Approval UX

严格区分：

```text
Planning Decision
```

和：

```text
Execution Approval
```

如果用户已经说：

```text
“把它改到下午。”
```

这已经是业务意图。

Agent 不应该再次问：

```text
“你确定要改吗？”
```

应该：

```text
调用高风险 Tool
↓
HITL
```

由统一 Approval UX 承担最后确认。

避免：

```text
Chat Confirmation
+
HITL Confirmation
```

重复。

---

# 五十、错误恢复也属于用户体验

正常用户不应该看到：

```text
ValidationError
Pydantic error
Naive datetime
Tool schema mismatch
```

Agent Harness 应：

```text
Tool Error
↓
机器可读 error code
↓
模型修复
↓
继续流程
```

只有：

```text
无法自动恢复
需要用户提供新信息
```

时才打断用户。

统计：

```text
Self Recovery Rate
```

但同时目标不是：

> “错误很多但都能重试”。

最终还应该降低：

```text
First-call Error Rate。
```

---

# 五十一、Plan Preview UX

用户最终关心的不是：

```text
Tool 返回了哪些 JSON。
```

而是：

```text
我要做什么
什么时候做
哪些没排进去
为什么
有哪些风险
是否需要我决定什么
```

最终回复尽量稳定表达：

```text
已安排

未安排

关键取舍

需要用户决定的唯一问题

下一步可执行动作
```

但不要机械输出所有 section。

简单计划保持简单。

---

# 五十二、Unplaced Task 必须可解释

Agent 不应该只说：

```text
3 个任务没排进去。
```

应该利用 deterministic reason codes：

```text
insufficient_free_capacity
deadline_before_available_slot
outside_work_hours
locked
dependency_not_satisfied
```

转换成自然语言。

LLM 负责：

```text
解释
```

Service 负责：

```text
事实 reason code。
```

---

# 五十三、研究“最少操作完成目标”

增加一个 Experience 指标：

```text
Interaction Efficiency
```

例如：

```text
User Goal Completion
/
(User Turns + Model Calls + Tool Calls)
```

不一定真的用一个总分。

重点比较：

```text
当前 Harness

vs

优化 Harness
```

是否从：

```text
3 Model Calls
5 Tool Calls
2 Clarifications
```

下降到：

```text
2 Model Calls
3 Tool Calls
0~1 Clarification
```

且质量不下降。

---

# 五十四、减少“Agent 味”

最终体验不要让用户感觉系统一直在：

```text
分析
确认
验证
检查
重新检查
```

这些内部复杂度应该被 Harness 吸收。

用户看到的应该更像：

```text
“我已经按截止时间和你的下午偏好排好了。
周四容量不足，所以报销任务暂时没排进去。
其余安排如下……”
```

而不是把内部 workflow 展开给用户。

---

# 五十五、增加 End-to-End UX Judge

原来的 User Judge 主要判断：

```text
Schedule Quality
```

下一轮再加入：

```text
Interaction Quality
```

Judge 获得完整但脱敏的：

```text
User Message
Agent Messages
Tool Action Summary
Final Outcome
```

评价：

```text
是否问了不必要的问题
是否重复确认
是否啰嗦
是否让用户理解当前状态
是否出现内部错误
是否在等待审批时说错状态
是否提供真正有用的下一步
```

输出：

```text
Interaction Satisfaction
```

与：

```text
Planning Satisfaction
```

分开。

---

# 五十六、最终 Tool Architecture 输出

最终报告必须给出：

## Current Tool Map

当前 Tool 全图。

## Tool Problems

例如：

```text
overlap
too fine
too broad
low frequency
high ambiguity
large response
large schema
```

## Final Tool Map

明确：

```text
保留
合并
隐藏
下沉
删除
```

哪些 Tool。

## Dynamic Surface

不同 Intent / Phase：

```text
平均暴露多少 Tool
最大暴露多少 Tool
```

## Before / After

例如：

```text
Registered Tools:
44 → 38

Average Visible Tools:
18 → 7

Average Tool Calls:
4.2 → 2.8

Invalid Tool Args:
x% → y%

Token:
29.7k → ...

Latency:
9.4s → ...
```

注意：

> Registered Tool 数量不是最核心指标。

我更关注：

```text
Average Visible Tools
Tool Calls
Selection Accuracy
Context Tokens
User Turns
```

---

# 五十七、工具优化停止条件

只有满足：

```text
Capability 不丢失

Correctness 不退化

HITL 不被弱化

Planning Quality 不显著下降

Tool Selection 更稳定

Invalid Args 减少

Token / Latency 或 Interaction 至少有明显改善
```

才接受新的 Tool Architecture。

如果：

```text
44 → 25
```

但：

```text
一个 Tool Schema 变成巨大 union
模型参数错误增加
Policy 更难维护
```

则应该回滚。

---

# 五十八、最终目标

最终不是追求：

> “TimeAgent 只有很少的工具。”

而是：

> **TimeAgent 拥有一个模型容易理解、Harness 容易控制、Service 容易保证正确、用户很少感受到内部复杂度的 Action Space。**

理想状态类似：

```text
用户
 ↓
一句自然语言目标
 ↓
Agent Harness
 ↓
只暴露当前阶段需要的少量 Tool
 ↓
最少必要 Tool Calls
 ↓
可靠 Deterministic Services
 ↓
必要时一次 HITL
 ↓
清晰结果
```

本轮应同时优化：

```text
Tool Architecture
Tool Surface
Context Size
Tool Result Size
Clarification
Approval
Error Recovery
Plan Presentation
Latency
Token Cost
```

而不是单独优化 Tool Count。
