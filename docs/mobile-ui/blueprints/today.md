# Today Blueprint — Execution Home

Status: V1 Iteration 1 implemented; browser review recorded in `../mobile-ux-v1-report.md`.

## User goal and priority

In a few seconds, answer: “What should I do now?” Priority is active task/current event → next scheduled item → progress → actionable risk → day closing. Low-frequency brief/reminder navigation is secondary.

## Data and business boundary

Use `useTodaySummary()` and the response from `TodayService`. `execution_now`, `execution_next`, `execution_later`, completed tasks, unfinished tasks, conflicts and reminders are facts from the API. The client may choose a presentation focus and count already-provided rows; it must not regroup items by local clock or infer schedule availability.

Implementation: `frontend/src/pages/today-page.tsx`, `frontend/src/components/today/execution-surface.tsx`, `frontend/src/components/today/day-closing.tsx`, `frontend/src/features/today/`.

Iteration 1 implementation: mobile focus is the first backend-provided `execution_now` item, otherwise the first `execution_next` item, otherwise one assistant action. Remaining next items stay visible; Later and Morning Brief are disclosures. Desktop execution surface remains unchanged. Day Closing behavior remains unchanged; the harvest surface contrast was simplified.

## Information hierarchy

1. Page title/date and a compact greeting/summary;
2. one execution focus: first `execution_now` item if present; otherwise first `execution_next` item; otherwise a calm empty state with one plan action;
3. remaining Next items as readable schedule rows;
4. Later, collapsed or summarized;
5. task completion progress and important actionable risks;
6. reminders, morning brief and harvest/day closing as secondary content.

The `execution_now`/`execution_next` precedence is a render choice over server-owned lists, not a client time classification. If multiple current items exist, the focus surface identifies one and links to the full section.

## Low fidelity wireframe

```text
┌──────────────────────────┐
│ 今天                     │
│ 10 月 5 日 · 星期一       │
│                          │
│ 正在进行 / 接下来         │
│ 写项目报告               │
│ 14:30–16:00              │
│ [完成]        [调整]      │
│                          │
│ 接下来                   │
│ 16:30  周会              │
│ 18:00  跑步              │
│                          │
│ 今日进度       2 / 5      │
│ ⚠ 一项安排需要处理        │
│ 今日收获       整理明天 › │
└──────────────────────────┘
│ 今天   助理   计划   我的 │
└──────────────────────────┘
```

## States

- Loading: brief inline progress; no empty-state flash.
- Empty: explicit no-plan message and one primary “让助理安排” action; adding a task is secondary.
- Partial: preserve loaded summary while optional insights/reminders fail; show local retry only for the failed feature.
- Error: state that Today could not load and offer retry; do not display stale data as current without marking it.
- Offline: retain cached data only when visibly labeled stale; hide unsafe writes or let the API reject them clearly.
- Conflict/risk: inline summary opens the affected item or Insight; only immediate blockers receive a prominent alert.
- Completion: completion is saved first and confirmed in a fixed, non-layout-shifting notice. Optional Harvest opens only when the user selects “记录反馈”; closing the Drawer preserves the pending interaction, while “跳过” explicitly dismisses it. A completed task can be restored from the notice or the expanded Today closeout section.

## Interaction and dimensions

Primary actions use 48 px targets. Secondary icons use 44 px minimum. Place the hero action above fold on 360–430 px widths; allow vertical scroll, never horizontal page overflow. Bottom navigation clearance includes system inset. “Later” and explanation copy are progressively disclosed.

## Accessibility

Use a single h1 and ordered section headings. Actions name the task. Loading/error/completion status is announced once. Completion feedback does not expand or reorder Today; focus enters the Drawer only after the user opens it. Text contrast follows `accessibility.md`.

## Browser and Android checks

Exercise idle day, active task, next event, conflict, completion + Harvest, error, five target widths and desktop >=1024 px. Physical Android keyboard/system bars/TalkBack are tracked separately and never inferred from Playwright.

## V2 — visual hierarchy pass

### Before / After / Reason

- **Before:** actionable risks sat inside a large warning surface with icon-only actions competing for the title and evidence text; deadline evidence could appear as raw ISO/UTC.
- **After:** risks are a plain section with left-accent divider rows. The full title, summary, and localized deadline come first; the common “稍后提醒” action has a visible label and low-frequency actions sit under “更多操作”. The page states the timezone used for displayed times.
- **Reason:** preserve room for the product fact and make touch actions understandable without hover; timezone formatting belongs to the user's locale, not the wire representation.
- **Harvest:** the zero-completion state remains a lightweight section and plain status row; completed work can add content, while one current execution focus remains the only prominent focus card.

The V2 screenshot set is in `../evidence/v2/`. Browser viewport captures verify layout and behavior only; Android visual acceptance is still pending.
