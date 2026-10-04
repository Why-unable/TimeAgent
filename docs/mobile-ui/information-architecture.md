# Mobile Information Architecture

## Decision

底部主导航采用四个稳定入口：

1. **今天** — Execution Home；
2. **助理** — Time Steward 对话；
3. **计划** — 日历、任务和排程相关页面；
4. **我的** — 提醒、洞察、简报、审批、偏好、记忆、通知、账户和应用设置。

`我的` 当前以分组的行列表 Drawer/Sheet 承载，避免新增低价值空白页面。`计划` 的移动入口打开 `/schedule` Plan Hub；日历、任务和规划仍可直接访问 `/calendar`、`/tasks` 和 `/planning`。

## Why

当前底栏将 `/calendar`、`/tasks`、`/planning`、`/reminders` 都标为“日程”，同时把低频功能放在“更多”的卡片网格里。用户必须先理解实现路由，不能从入口名预知功能。新结构以行动周期分组，而不是按桌面页面名称分组：执行、求助、计划、个人管理。

计划区域中的日历/任务/规划子页面是区域内目的地，不再和底部入口并列为 App 一级目的地。手机端 Plan Hub 提供日期选择、当天事实和未安排任务预览；桌面继续保留现有导航。

## Route mapping

| Destination | Mobile entry | Existing route / behavior |
|---|---|---|
| Today | 今天 | `/today` |
| Assistant | 助理 | `/chat` and `/chat/:conversationId` |
| Plan | 计划 | `/schedule`; `/calendar`, `/tasks`, and `/planning` remain directly addressable |
| Me | 我的 | grouped mobile drawer linking existing low-frequency routes |

Desktop navigation remains unchanged. Deep links keep their current route and select the appropriate mobile destination.

## Planned destinations within Me

时间服务：提醒、洞察、简报、审批。个性化：时间偏好、时间行为记忆。设置：通知、账户与安全、应用设置；staff-only system status remains permission filtered. Reminders are visible from Today and remain reachable from Me. V1 keeps these destinations in the shared Me Drawer/Sheet; it does not add a separate Me landing page because each destination already has a real route.

## Migration stages

- Iteration 1: shell navigation, Today, Assistant.
- Iteration 2: Plan Hub, mobile Calendar and Tasks.
- Iteration 3: focused Planning interactions, Reminders, Me destination screen, Approvals, Memory and remaining low-frequency pages.

## Evidence and limits

The initial route audit is source-level; journey frequency has no trustworthy mobile analytics denominator. Grouping is a product hypothesis to validate in browser and with users, not a measured preference claim. See [Today](blueprints/today.md), [Assistant](blueprints/assistant.md), [Plan](blueprints/planning.md) and [More/Me](blueprints/more.md).
