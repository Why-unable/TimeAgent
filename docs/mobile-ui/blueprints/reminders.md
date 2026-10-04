# Reminders Blueprint — Iteration 3

Status: Iteration 3 implemented after independent blueprint review.

## Audit findings

- Today and Me link to `/reminders`. On mobile the page has no visible page heading; the complete create form is always expanded before the reminder list.
- Create success is not announced, create/cancel errors are not actionable, and list-load failure has no retry.
- A failed item is mixed into “待发送”; cancelled items disappear from every section. A list containing only cancelled items renders no explanation.
- Cancel is icon-only and below the 44 px touch target.

## Mobile jobs and hierarchy

1. See the next reminder status and due time.
2. Create one reminder with content, local time and an optional linked task/event.
3. Recover from failed delivery, create/cancel rejection, or list-load failure.

Mobile shows a visible `提醒` title and one `新建提醒` action. That action opens the shared Drawer containing the focused form. Use concise field labels for reminder content, time (`IANA timezone` displayed), and optional association. The native date/time picker is an acceptable input; conversion to UTC, gap/fold validation and idempotency remain in the existing form and API.

List failed reminders under “需要处理”; pending/queued/sending under “待发送”; sent/missed under “最近记录”; cancelled reminders remain queryable in a collapsed “已取消” section. Do not imply that a saved console reminder guarantees Android notification delivery; notification permission and channels stay in Notification Settings.

## States and errors

- Loading, error and empty are mutually exclusive: short status line while loading, retry alert on error, and no empty state until fetch succeeds.
- Empty: “还没有提醒” and one create action.
- Partial/populated: section counts; keep pending first and cap history as today.
- List error: explain loading failed and provide retry.
- Create error: retain entered fields, explain the actionable server/time validation reason, allow retry; on success close the Drawer, reset idempotency key and announce creation.
- Cancel error: keep the reminder visible, announce failure near it and allow retry. Cancel remains disabled only while the request is pending.
- Offline/stale: do not claim data is current or convert failed data into an empty list; use existing query state and explicit retry.
- DST gap/fold and invalid/past times: preserve current timezone validation and surface a field-level message.

## Accessibility and acceptance

- Drawer uses the shared title, close, focus trap/restore, Escape/Android Back and safe-area contract.
- Labels reference their errors; submit failure focuses the first invalid field. Status/error uses `status`/`alert`.
- Primary and row actions are at least 48 px; icon cancel has a visible text equivalent or a 44 px named target.
- E2E covers Me and Today entry, create-sheet open/close, local timezone serialization, success, invalid time, list retry, failed/cancelled grouping, cancel failure, 320 px no overflow, and 360–430 px screenshots.
- Android notification permission, system alarm and native picker behavior are `NOT EXECUTED` without a connected device.
