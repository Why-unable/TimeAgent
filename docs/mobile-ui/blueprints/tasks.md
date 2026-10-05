# Tasks Blueprint — Iteration 2

Status: Iteration 2 mobile implementation complete; preserve Task API and execution semantics.

## Audit evidence and limits

- `/tasks` renders the shared Calendar/Tasks/Planning/Reminder tab strip, three primary filters, five extra filters, a free-time recommendation card, project groups, full descriptions, due/planned-time boxes, and up to seven icon actions for every task.
- This creates a long, equal-weight stack on phones. Several secondary feedback buttons do not meet the documented 44 px target. No analytics data is available to claim which filter is used most.
- `filterTasks` and the Task API already distinguish due time, planned time, status, timezone and execution signals. Do not duplicate or alter that business meaning.

## Mobile hierarchy

1. Page title and one clear “新建任务” action.
2. Three common filters (`收件箱`, `今日任务`, `即将到期`) in a horizontal, keyboard/touch-accessible row; less common filters stay behind “更多筛选”.
3. Task rows grouped by project only when that grouping adds information. Each row leads with title and status, then the useful due/planned context and estimate.
4. One filled main execution action for the current task state (start/resume or pause); complete remains a clear secondary action. Skip, edit, execution summary, and estimate feedback are subordinate under “更多操作”.
5. Free-time recommendations are secondary and collapsed by default on mobile; finding a slot never creates an event/task automatically.

Desktop keeps the current full task detail and all task actions visible. Task create/edit continues to use `TaskEditor`.

## States and semantics

- Loading: loading message/skeleton, not empty state.
- Empty inbox: explain how to add a task; “新建任务” remains visible.
- Filtered empty: name the active filter and offer a path to Inbox/All.
- Populated: visible status text, due time distinct from planned time; task labels remain readable with long titles at 320 px.
- Complete/start/pause/skip: retain existing endpoints/signals and mutation feedback; do not infer task completion locally before API success.
- Edit/create: existing editor, labels, validation and timezone-aware serialization remain intact.
- Summary/recommendation: collapsed optional region, explicit loading/error, feedback controls at least 44 px; keep the feature opt-in.
- Offline/error: preserve actionable API error and retry behavior where currently available; do not present failed data as an empty inbox.

## Acceptance

- Common filters are visible without forcing the optional recommendations into the first screen; announce selected filter with `aria-pressed` and a non-color visual state.
- All required actions have accessible names that include the task title; hitboxes are at least 44 × 44 CSS px and preferred primary actions are 48 px.
- Verify 320/360/375/393/412/430 widths for no horizontal page overflow, long titles, empty/populated/filtered states, and expanded optional actions.
- Existing test coverage for due-vs-planned distinction, timezone serialization, complete, start/pause/skip, execution summary, and feedback remains valid.

## V2 — visual hierarchy pass

### Before / After / Reason

- **Before:** filters were visually nested in a panel, ordinary tasks had separate card boundaries and boxed timestamps, and the free-time recommendation appeared ahead of the task list.
- **After:** filters sit directly in the page flow; selected filters use one fill and stronger text weight with `aria-pressed`. Tasks use project grouping and divider rows; time is plain labeled metadata in the user's timezone. Recommendations follow the tasks in a lightweight disclosure.
- **Reason:** tasks are a list of comparable items, not independent dashboard panels. Keep a boundary only for a separate semantic focus/decision surface.

After completion, the polite live announcement remains available to assistive technology and keyboard focus returns to the visible “任务列表” heading. The page description states its display timezone. V2 browser captures are under `../evidence/v2/`; Android/TalkBack review is still pending.
