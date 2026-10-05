# Mobile UX V2 — De-cardification / Visual Hierarchy Report

- Date: 2026-10-05
- Branch: `main`
Scope: frontend visual hierarchy and mobile regression coverage. Mobile IA, APIs, backend rules, scheduling, Agent behavior, and HITL semantics were not changed.

## Initial findings

Three Android screenshots supplied by the user showed the mobile app still reading like a dashboard: the task list squeezed a long title and status metadata into narrow boxed columns; Today used a dark gradient with low-contrast explanatory text and an overemphasized empty-day area; Plan stacked bordered date, agenda, and task surfaces, while the goal field was difficult to use at phone width. Across these screens, ordinary sections used rounded borders and tinted backgrounds where spacing and dividers were enough.

The source PNGs are 1272 × 2800 portrait captures. They remain the pre-change references supplied in the conversation and were not copied into the repository. The connected post-change device identifies as `PLR110`, Android 16, with a 1272 × 2800 display at 560 dpi.

## Surface inventory

| Screen | Main structure after V2 | Retained surface and reason |
|---|---|---|
| Today Alerts | Plain section, left accent, divider rows; full risk text precedes actions | Action control boundaries only |
| Today Harvest | Plain section and text-only empty state | One current-execution focus card elsewhere on Today; Harvest can gain content when work is completed |
| Plan Hub | Week, agenda, and unplanned work are sections/rows separated by spacing and dividers | Date selection controls and one primary planning action |
| Tasks | Grouped divider rows; filters sit in page flow | Focus/warning states only when semantically needed |
| Reminders | Status headings and divider rows | One modal Drawer for the create form; native input controls retain their field boundaries |
| Approval | One decision surface per independent high-risk proposal | Amber decision surface expresses a pending user decision; preview/editor details are divider rows |

Ordinary pages target zero nested surfaces and no more than two large bordered surfaces in the first viewport. Approval is the intentional exception with one surface per independent proposal; fields and controls are not counted as section cards.

## Screens changed — before / after / reason

### Today

- **Before:** warning cards contained task cards and icon-heavy controls; deadlines could appear as raw UTC/ISO values. Harvest occupied a prominent panel even when nothing was complete.
- **After:** alerts are flat, readable rows with visible “稍后提醒”; secondary actions are disclosed on demand. Alert dates/deadlines use `formatInUserTimezone()` and the profile timezone is visible. Empty Harvest is a low-emphasis section; completed items render as rows.
- **Reason:** show the user’s current facts and next action without asking them to decode a wire timestamp or card hierarchy.

### Plan Hub

- **Before:** week selector, day agenda, and unplanned tasks each had their own large card, with date chips nested in the week card.
- **After:** sections use headings, spacing, and dividers. Seven dates fit from 360 px upward; at 320 px a horizontally scrollable 44 px target rail displays a visible “左右滑动可查看其余日期” hint. The main planning action remains above bottom navigation.
- **Reason:** dates are controls; the groups around them do not need additional physical containers.

### Tasks

- **Before:** filter panel and ordinary task rows read as separate cards; task disclosures had generic accessible names.
- **After:** filters sit directly in the page flow and the selected filter has one filled state. Task lists use divider rows, display timezone context, and move the visible focus to “任务列表” after completion. “更多操作” names include the task title.
- **Reason:** tasks are comparable list items, and secondary actions should be understandable without relying on hover or color alone.

### Reminder

- **Before:** desktop slate background classes leaked into mobile and made each reminder look like a card. The create Drawer had large unused space below the primary action; group titles skipped a heading level.
- **After:** status groups use flat reminder rows and readable text badges. The shared Drawer fits short content up to a viewport max height; sections and reminder titles follow `h1 → h2 → h3`.
- **Reason:** one modal surface is justified for reminder entry; the records themselves belong to status lists.

### Approval

- **Before:** the proposal surface was justified, but change preview rows, details, and batch editor fieldsets also appeared as nested surfaces. Repeated generic action names were ambiguous across proposals.
- **After:** each ActionProposal keeps one semantic decision surface. Changes and batch editor groups use dividers; actual input controls keep their boundaries. Approve, edit, reject, and recurring-instance actions include the object name where available.
- **Reason:** the high-risk decision needs a clear boundary; supporting content does not. Contextual accessible names identify which proposal an action affects.

## Removed nested surfaces

- Today’s risk wrapper and inner task cards were replaced with a single flat alert list.
- Plan Hub’s outer week card and separate agenda/task cards were removed.
- Tasks’ filter wrapper and ordinary task cards were flattened into rows.
- Reminder row backgrounds that were unintentionally enabled by responsive compatibility selectors were removed on mobile.
- Approval preview backgrounds, editor details background, and batch-editor fieldset cards were removed. The independent decision surface, real form controls, and meaningful warning/conflict states remain.
- Browser assertions check that the Approval decision surface has no nested `data-surface` and that ordinary mobile Harvest is marked `data-surface="none"`.

## Timestamp and timezone handling

Changed Today alert due times are formatted using the user’s IANA timezone and locale with the existing frontend date utilities. The timezone is disclosed in the Today view. Reminder and Approval times continue through `formatInUserTimezone()`; raw ISO/UTC strings are not used as user-facing text in these changed surfaces. Database/API timestamp contracts are unchanged.

## Critic results

The Mobile Visual Critic, Product UX Critic, and Accessibility Critic independently reviewed the first four screens and the final Reminder/Approval screenshots.

- Product UX initially identified excessive blank space below the reminder create action (P2); content-sized Drawer behavior fixed it.
- Accessibility initially identified a skipped heading level in Reminder groups and the Drawer (P2); ordered headings fixed it. Approval action names now carry proposal context.
- Final independent review found no remaining P0, P1, or P2 issue in Reminder or Approval. The first-four-screen review also passed after the 320 px Plan spacing adjustment.

## Evidence

Playwright screenshots are under [`evidence/v2`](evidence/v2/):

- Today populated and empty: [`today-393.png`](evidence/v2/today-393.png), [`today-empty-393.png`](evidence/v2/today-empty-393.png)
- Plan and Tasks at 320, 360, 375, 393, 412, and 430 CSS px
- Calendar and agenda at the target widths
- Reminder create/list: [`reminder-create-393.png`](evidence/v2/reminder-create-393.png), [`reminders-list-393.png`](evidence/v2/reminders-list-393.png)
- Approval: [`approvals-393.png`](evidence/v2/approvals-393.png)

These browser captures verify layout and behavior only. The user-supplied baseline screenshots are recorded above; post-change Android evidence is documented separately below.

### Physical Android verification

The connected `PLR110` (Android 16, 1272 × 2800, 560 dpi) received a local QA build of the current working tree. The APK retained `com.timeagent.app`, `1.1.12 / versionCode 16`, and its signing certificate SHA-256 matched the installed/released `1.1.12` APK (`e7fb9f63eff74b44c3ec32dafdcb2c726ff2d031c5c7614f70dda486916a783e`). It was installed with `adb install -r`; existing app data was preserved. This QA build was not copied to `releases/` or published.

On-device visual checks passed for Today and expanded Harvest, Plan Hub, Assistant, the Me drawer, Reminder list, and Reminder create Drawer. Harvest text remained readable on the light page surface. The planning action stayed above the bottom navigation. With the Android IME open, the Assistant composer remained visible and the mobile navigation hid; pressing Android Back to dismiss the IME restored the navigation. In the Reminder Drawer, scrolling with the IME open brought the complete create action into view.

The first IME pass exposed a keyboard-detection gap on this Android WebView: it resizes `window.innerHeight` and `visualViewport.height` together, so their difference remains small. Mobile navigation now also compares the current height with the last unobscured viewport height. The navigation regression test covers both IME open and close; the retest on this device confirmed the navigation hides and restores correctly.

A follow-up chat-specific device pass reproduced two additional issues: horizontal quick actions clipped the last option with no visible scroll cue, and the composer sat about 100 CSS px above the keyboard because the chat panel kept reserving its normal bottom-navigation clearance after Android resized the viewport. Quick actions now wrap into a two-column grid on phones. When the IME resizes the viewport, the chat panel expands to the available height; when the keyboard overlays rather than resizes the viewport, the existing visual-viewport offset behavior is retained. On `PLR110`, all four quick actions were visible, the composer and send button met the keyboard edge, and Android Back restored the composer above the bottom navigation.

Physical captures are under [`evidence/v2/android-plr110`](evidence/v2/android-plr110/): Today, expanded Harvest, Plan, Assistant quick actions and IME open/closed, and Reminder list/create/IME states.

TalkBack, full Android Back route/history behavior, notification deep links, local alarm behavior, and alternate system navigation modes were not exercised and remain `NOT EXECUTED`.

## Automated validation

- Vitest: 195 passed across 38 files.
- After the device-discovered IME fix, `tests/mobile-navigation.test.tsx`: 11 passed, including keyboard-open and keyboard-close behavior.
- Chat page unit tests: 12 passed. The focused mobile Playwright run passed 3 tests for visible quick-action wrapping, overlay keyboard avoidance, and the Android-style resized viewport.
- ESLint: passed.
- Vite production build: passed after the IME fix. Existing warnings remain for Capacitor static/dynamic import mixing and a main chunk over 500 kB.
- Android release variant: `assembleRelease` passed with the existing signing identity; the local QA APK installed successfully over the existing app.
- Playwright desktop Chromium: 39 passed, 9 skipped, 0 failed.
- Playwright mobile Chromium: 40 passed, 2 skipped, 0 failed.
- Django `manage.py check`: passed.
- `makemigrations --check --dry-run`: no model changes detected. PostgreSQL at localhost:5432 was unavailable, so Django could not verify migration-history consistency.

## Acceptance and known gaps

- **Main action visible:** yes; planning, reminder creation, and approval actions remain explicit.
- **Every section boxed:** no; ordinary sections use typography, spacing, dividers, and rows.
- **Nested cards:** none in the reviewed ordinary mobile surfaces; the Approval card is the single independent decision surface, with form controls/warnings retained where semantically required.
- **Hierarchy:** primarily typography, spacing, status text, and divider rhythm.
- **Accent color:** reserved for selection, primary actions, active state, risk, and completion.
- **Empty states:** lightweight text and one relevant action.
- **Assistant:** quick actions wrap on phone widths; the composer stays adjacent to the IME and returns above navigation when it closes. No conversation model or flow changed. Me received no structural redesign in this pass.
- **Physical Android verification:** visual surfaces and the IME/navigation interaction passed on `PLR110` / Android 16; the native scenarios listed above remain unverified.

The local QA APK is only a device-test artifact. No commit, push, merge, production deployment, release tag, or public Android package was produced in this pass.

## 2026-10-05 — Today completion recovery follow-up

Today completion feedback now stays out of the page flow. Completing a task shows a fixed status notice; “记录反馈” opens the shared Drawer only after an explicit tap. Closing the Drawer preserves the pending feedback interaction, and the expanded “今日收尾” area retains a recovery action for completed tasks.

The reported “暂时无法关闭反馈卡” path came from validating an empty JSON object as a blank field even though `dismiss` correctly requires empty values. `InteractionSubmission.values` now allows `{}`; dismissal remains explicit and is stored with its idempotency key. Failed dismiss requests keep the Drawer and retry control available with HTTP status and request ID. Restoring a completed task writes an idempotent `reopened` execution signal, returns it to pending through `TaskService`, abandons its pending completion-feedback artifact, resynchronizes reminders, and preserves audit history.

Validation for this follow-up: frontend focused tests **21/21 passed**, ESLint passed, Vite production build passed; backend focused tests **41/41 passed**, Django system check, migration drift check and Ruff passed. OpenAPI and frontend generated types include the new execution-signal enum. Updated physical-device verification was not run as part of this follow-up.

## 2026-10-05 — Production release and Android Studio emulator follow-up

Commit `aeb28d7` was pushed to `main` and deployed to the local production Compose stack. The release package is `1.1.13 / versionCode 17`; its signature matches the prior production APK. The in-app update service now advertises the release, and the public APK download matches the recorded SHA-256 and byte size. Local and public readiness checks returned HTTP 200.

An Android Studio Medium Phone AVD (Android 16/API 36) exercised the staging build on a 411 CSS-pixel viewport. All four assistant quick actions fit without horizontal overflow; the composer remained next to the software keyboard. On Today, completing a staging E2E task opened feedback only in a Drawer; skipping succeeded without an error, and the persistent recovery action restored the task to unfinished. This is emulator evidence against isolated staging, not a physical-phone production-upgrade test.
