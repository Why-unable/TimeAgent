# Plan Hub Blueprint — Iteration 2

Status: Iteration 2 Plan Hub and Iteration 3 mobile Planning interaction are implemented. Preserve plan draft, expected-version, UTC and HITL semantics.

## Audit evidence and limits

- The mobile bottom-bar “计划” entry currently targets `/calendar`; Calendar, Tasks, Planning and Reminders also share `ScheduleWorkspaceTabs` on narrow screens.
- `CalendarPage` already reads events through `useEvents`; `TasksPage` reads task records through `useTasks`; `/planning` owns draft creation and editing. The client must not derive schedule feasibility, conflict or approval outcomes.
- There is no product analytics evidence in this repository showing which plan job is most frequent. The information order below is a usability hypothesis based on the entry point, route structure, and available user tasks; it is not a measured frequency claim.

## Primary mobile jobs

1. Check what is on a chosen day.
2. Find active tasks that do not yet have a planned start.
3. Move into the existing planning flow to ask for a draft, review it, and use existing approval paths.

## Route and hierarchy

The mobile Plan tab opens `/schedule`, a lightweight overview. Existing `/calendar`, `/tasks`, `/planning`, and `/reminders` routes remain valid. The desktop sidebar continues to open `/calendar` and keeps its current navigation semantics.

```text
计划 · 10 月 5 日
[上周]  周一 5  周二 6  周三 7  ...  [下周] [本周]

10 月 5 日 · 星期一                 [新建日程]
09:30  项目评审                     [open calendar]
10:00  写项目报告                    [planned task]
没有日程或计划任务时显示明确空状态

待安排任务 · 3 项                    [全部任务]
任务标题 · 截止时间
任务标题 · 未设截止

[让助理起草安排] → /planning
```

- A compact seven-day date rail pages by week using visible Previous week / Next week / This week controls; do not require swipe alone to reach another week. Every date button exposes a complete local-date accessible name and a non-color selected state; the selected date is scrolled fully into view.
- The selected-day agenda merges calendar events from `useEvents` and scheduled task intervals from `useTasks` (`planned_start_at` / `planned_end_at`). These intervals are separate records and must not be assumed to have matching CalendarEvents. Show a text type label and sort by start instant for presentation only.
- Cap each section at three previews so the main planning action remains reachable on a busy day; “查看全部日程” and “全部任务” open their focused routes.
- Event editing remains in the existing calendar flow. Event creation is a secondary text action; “让助理起草安排” is the single filled primary action.
- Show a short list of pending/in-progress tasks without `planned_start_at`; label due time separately from planned time. “全部任务” opens `/tasks`.
- The single primary planning CTA opens `/planning`. The hub does not create, apply, or approve plans by itself.
- Date calculations and API ranges use `getLocalDateKey` and explicit timezone conversion. Do not compare UTC date substrings or infer availability locally.

## States

- Loading: render section-level skeleton/status; avoid flashing “no events/tasks” before each request settles.
- Partial: event and task areas report their own errors and can be retried independently if supported; a failed task request must not hide a successfully loaded agenda.
- Empty agenda: state that the day has no events and link to Calendar; do not imply the day is available for work.
- Empty unplanned tasks: show “当前没有待安排任务” and keep the Calendar and planning destinations visible.
- Populated: maximum three unplanned task rows, then a “全部任务” link; event list remains scrollable with page flow.
- Stale/offline: rely on existing React Query/API behavior; do not label cache fresh or fabricate a stale-data state.
- Draft, applied, stale, or approval failure: owned by `/planning`, the chat, and existing HITL proposal surfaces; the hub only routes there.

## Acceptance

- The bottom Plan item opens `/schedule`; `/calendar`, `/tasks`, and `/planning` remain directly addressable and keep the Plan item active.
- Select each day in the rail and verify event range and displayed local date agree. A deterministic Asia/Shanghai fixture checks an event crossing UTC midnight and the expanded UTC query range; live account/staging behavior remains a separate environment check.
- Verify planned tasks appear in the selected-day agenda even if there is no corresponding CalendarEvent; unplanned tasks appear in their separate preview.
- Test a busy selected day with at least six calendar events and verify the planning CTA and route links remain reachable.
- Verify independent loading/empty/error states and no horizontal page overflow at 320, 360, 375, 393, 412, and 430 CSS px.
- Do not claim frequency research or real Android behavior based on mocked-browser checks.

## Iteration 3 — Mobile Planning interaction

### Mobile job and hierarchy

The Plan Hub's `让助理起草安排` remains the clear path for an ambiguous goal. `/planning` must identify that path as “让助理起草计划” and say the draft is reviewed before any formal apply. A user with a concrete task/time edit can use the existing plan interaction controls without restating known state.

```text
计划草案 · 尚未应用
任务名                     09:30–10:30
[调整时间与时长]
未安排 · 1 项              原因…

[提交应用审批]
```

On phones, tapping “调整时间与时长” opens a shared Drawer for an eligible item with local start time, duration, −15/+15 minute controls, save, and clear failure/stale feedback. Only a single-segment, placed, unlocked task is editable; split, unplaced or locked items show a reason and the correct alternative (unlock first, or use the existing plan regeneration flow). Drag remains an optional enhancement; keyboard/buttons are always available. A successful edit keeps the plan as a draft and updates the version; applying still goes through ActionProposal + HITL in Chat. Desktop timeline controls remain in place.

Each accepted time edit continues through the existing plan interaction/application endpoint with the expected version and timezone-converted UTC start/end. A ±15-minute action changes the start and preserves the current duration. The frontend reports API conflicts but does not decide slot feasibility.

Capacity is secondary and must show the selected time range beside the capacity values. Manual task/range/strategy controls remain behind the existing progressive disclosure; do not duplicate planner decisions in the browser.

### States and acceptance

- Drawer has a task title, accessible controls, close/Back/focus restoration, safe-area and keyboard reachability.
- A save shows pending state, success while preserving “draft”, API validation/conflict errors, and a path to reload the latest plan. Mobile rejection and stale-refresh feedback stay visible inside the open sheet.
- A failed interaction restore remains retryable. Stale plan versions block repeated submission until refreshed.
- E2E covers tap-to-edit without drag, local-to-UTC serialization, step buttons, successful save, locked/split/unplaced item affordances, 409 recovery, and no apply/approve request from the timeline editor.
- Loading/error/offline states remain owned by existing hooks and API; no planning or apply logic moves client-side.

## V2 — Plan Hub visual hierarchy

### Before / After / Reason

- **Before:** the week selector, selected-day agenda, and unplanned tasks each used a bordered rounded container, with the date buttons nested inside the week card.
- **After:** these are plain sections separated by spacing and dividers. All seven dates fit in a single grid; the selected date uses a single filled state and `aria-pressed`. Agenda and unplanned items use divider rows; the planning CTA remains the only filled primary action.
- **Reason:** the date buttons need an interactive selected state, but their section does not need a separate physical boundary. Showing all seven dates also makes the end of the week discoverable without implying horizontal scroll.

Empty agenda states use concise text rather than a dashed card. V2 browser captures are stored under `../evidence/v2/`; this is not a substitute for Android device review.
