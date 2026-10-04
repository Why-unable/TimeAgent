# Mobile UX Acceptance Checklist

## Stage 1 — Mobile Shell, Today, Assistant

- [x] Four destinations are Today, Assistant, Plan, Me; Calendar/Tasks/Planning and Me deep links map to the expected destination.
- [x] Bottom bar is light, compact, fixed, safe-area aware and uses 48 px targets; active state has weight, icon backing and screen-reader text.
- [x] Me exposes grouped low-frequency routes using rows; staff-only filtering is preserved.
- [x] Today uses a focus from server-provided buckets; it does not reclassify time in the browser.
- [x] Today puts the focus first, collapses Later and Morning Brief, offers retry after summary failure, and uses a high-contrast harvest surface.
- [x] Chat keeps the composer primary, uses lightweight prompt chips, preserves run/approval/error/cancel behavior, and does not force a reader at the bottom while streaming.
- [x] History is a modal Drawer with focus restoration, Escape and native Back listener lifecycle; a synthetic virtualViewport test confirms the composer moves above keyboard space and hides bottom navigation.
- [x] 360, 375, 393, 412 and 430 CSS px Today/Assistant screenshots were visually reviewed; 320 px reflow smoke passes.
- [x] Desktop workspace browser suite passes 7/7 when run serially.
- [x] Android debug APK builds. Device availability checked; `adb devices` was empty, so install, Gboard, TalkBack and system bars are `NOT EXECUTED`.

## Later stages

- [x] Plan Hub opens from Plan and shows selected-day events/planned tasks separately from unplanned tasks, with one Planning CTA.
- [x] Calendar uses mobile month date navigation + a day agenda Drawer; desktop FullCalendar views remain intact.
- [x] Tasks prioritize common filters and row actions with progressive disclosure for secondary filters/actions and recommendations.
- [x] Plan, Calendar and Tasks were visually reviewed at 360, 375, 393, 412 and 430 CSS px; agenda sheet reviewed at 393 px.
- [x] Verify Plan timezone-boundary behavior with a deterministic Asia/Shanghai fixture: a UTC event crossing midnight displays on the correct local date/time, and the event query range expands in UTC. This does not replace a live staging/account check.
- [x] Planning edits use a mobile time sheet for eligible placed single-segment, unlocked items; saves keep draft/HITL behavior on the existing API.
- [x] Plan edit rejection and stale-plan refresh feedback remain visible inside the open mobile time sheet.
- [x] Reminders use a focused mobile create sheet, account-timezone conversion, explicit status groups, and actionable retry/error states.
- [x] Approvals use a mobile filter sheet, compact long previews, and block stale edit payloads until reopened against the refreshed version.
- [x] Memory proposals show a human-readable value/reason; memory dates use the account timezone; destructive actions use a confirmation Drawer.
- [x] Me destinations use grouped rows; browser route changes close the Me Drawer. Day Closing behavior remains unchanged.
- [x] Planning, reminder, approval, and Memory mobile layouts pass 320/360/393/430 CSS px no-overflow checks where applicable; screenshots are saved under `evidence/`.
- [ ] Physical Android Back, IME, notification picker, TalkBack and system-bar checks remain `NOT EXECUTED` without a connected device.

## Final automated validation

- [x] Vitest: 194/194; ESLint; Vite production build.
- [x] Playwright: 77 passed, 11 skipped, 0 failed across desktop/mobile Chromium; fixtures use mocked APIs.
- [x] Django system check; migration dry run reports no changes (PostgreSQL unavailable for migration-history verification).
- [x] Android debug APK assembles; physical device validation remains not executed (`adb devices` empty).
