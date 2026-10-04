# Mobile UI Changelog

## 2026-10-04 — Mobile UX V1 foundation and Iteration 1

### Audit

- Before: bottom navigation labeled schedule while Calendar, Tasks, Planning and Reminders were treated as the same destination; More used large feature cards.
- After: design source of truth and staged IA documented; current implementation findings and production revision recorded.
- Evidence: repository source audit at `6b794ab`; production containers report `6b794ab`, readiness 200.

### Mobile Shell, Today and Assistant

- Before: Today showed rhythm, three statistics and Now/Next/Later panels at similar weight; Assistant empty state resembled a large landing page with large buttons; chat history was an uncontained overlay; streaming always forced the transcript to the bottom; mobile Me/settings routes were not grouped in the bottom bar.
- After: bottom bar now reads Today / Assistant / Plan / Me with route-aware active state; Me uses grouped rows. Today follows the server's `execution_now` then `execution_next` order for its focus, collapses Later and moves the morning brief below it. Assistant opens directly into chat with horizontal prompt chips, a keyboard-aware composer and follow-latest scrolling. History uses the shared accessible Drawer and Android Back handling. Today harvest uses a solid white surface with dark readable text.
- Browser evidence: Playwright mobile suite passed 18/18, including 320 px reflow, 360/375/393/412/430 px screenshots, active task / next event states, harvest contrast, history drawer and synthetic virtual-keyboard resize. Screenshots are in [evidence](evidence/).
- Automated checks: frontend unit tests 177/177, ESLint passed, Vite production build passed, Android debug APK build passed, Django system check passed. Migration check reported no changes; its local PostgreSQL history consistency check timed out. Desktop workspace browser suite passed 7/7 when run serially; an earlier concurrent Playwright invocation lost the shared Vite server and was discarded.
- Android evidence: `adb devices` reported no connected devices. APK installation / Gboard / TalkBack / native system bar checks are `NOT EXECUTED`.

### Stage boundary

- Plan Hub, Calendar, Tasks, Planning, Reminders and Approvals were not redesigned. Day Closing behavior was not changed. No production deployment or release tag was created by this iteration.

## 2026-10-04 — Iteration 2: Plan Hub, Calendar and Tasks

### Plan Hub

- Before: the Plan destination opened the desktop-oriented Calendar route; the mobile route gave no overview of a selected day plus unscheduled tasks.
- After: Plan opens `/schedule`, with a week date rail, selected-day agenda combining calendar events and planned task intervals, a separate unplanned-task preview, and one Planning CTA. Existing `/calendar`, `/tasks`, and `/planning` routes remain addressable.
- Date range construction uses explicit local date keys and timezone conversion. The selected chip scrolls into view, and the user can page weeks using named controls.

### Calendar

- Before: mobile reused FullCalendar week/day surfaces with horizontal scrolling and a dense month view.
- After: mobile uses a custom accessible month grid for date selection and the shared Drawer for the day agenda; desktop keeps FullCalendar month/week/day controls. Event CRUD, validation and timezone handling stay in the existing flows.
- Browser evidence: 360/375/393/412/430 CSS px screenshots and the 393 px day agenda are in [evidence](evidence/).

### Tasks

- Before: all filters, recommendations and secondary task actions competed for the same mobile space.
- After: common filters are visible; secondary filters, free-time recommendations and secondary actions are progressively disclosed. Completion recovery and action controls retain existing API semantics.

### Validation

- Vitest: 185/185 passed; ESLint and production build passed; Django system check passed.
- Playwright: **72 passed, 10 skipped, 0 failed** across desktop and mobile projects. Skips are project-specific or need live backend/staging configuration. Browser fixtures are mocked for the tested flows.
- Fixed a refresh race in Today completion feedback recovery: cancel any in-flight pending-interaction list request before installing the successfully retried artifact. Desktop and mobile recovery passed 6/6 repeated focused runs.
- Android device checks were not executed because `adb devices` returned no device. `makemigrations --check --dry-run` found no model changes; migration-history consistency could not be verified because local PostgreSQL was unavailable. No backend model or migration files changed.
- No commit, push, merge, production deploy, or release tag was created.

## 2026-10-04 — Iteration 3: Planning, Reminders, Approvals, Memory and Me

### Planning

- Before: mobile users had desktop timeline inputs and drag interactions without a focused touch path.
- After: eligible placed, unlocked, single-segment tasks open the shared Drawer with account-local start time, duration, ±15-minute controls, and save. Plan version, UTC conversion, server feasibility, draft state and HITL apply flow remain unchanged.
- Browser evidence: the mobile editor is captured at 393 CSS px and checked for overflow at 320 px.

### Reminders

- Before: the full form occupied the page, reminder states were hard to distinguish, and list/cancel errors offered no recovery.
- After: mobile exposes one focused create action and a labelled Drawer; form values retain timezone validation and idempotency. Failed, pending, recent and cancelled records have distinct sections; list and cancel failures expose retry; success is announced after the Drawer closes.
- Browser evidence: the create Drawer is captured at 393 CSS px; 320/360/393/430 px overflow checks pass.

### Approvals

- Before: six status chips used page space on narrow screens, long plans expanded every line, and an editor could retain an old payload after a proposal refresh.
- After: mobile filters use a shared Drawer; review shows three changes plus an exact-count disclosure; a refreshed proposal version marks the editor stale and blocks submission until it is reopened. Approval remains in the ActionProposal/HITL API.
- Browser evidence: the filter Drawer is captured at 393 CSS px; 320/360/393 px checks and the stale-version E2E pass.

### Memory and Me

- Before: memory dates used the device timezone, proposal reasons showed internal machine codes, stats were always expanded, and destructive actions used `window.confirm`.
- After: dates use the account/profile timezone; pending proposal values and reasons use readable labels/fallbacks; analytics can be expanded; privacy controls have visible focus and minimum touch targets; destructive actions use a titled, reversible confirmation Drawer with a clear/return choice. Me Drawer closes after route changes.
- Browser evidence: Memory screenshots cover 360/393/430 CSS px and readable proposals at 393 px.

### Validation

- Vitest: **194/194 passed** across 38 files; ESLint and Vite production build passed.
- Playwright: **77 passed, 11 skipped, 0 failed** across desktop and mobile Chromium. Skips follow existing project filters and missing staging/live-backend configuration; browser UX runs use deterministic API mocks.
- Django system check passed. `makemigrations --check --dry-run` reported no model changes; PostgreSQL was unavailable, so migration-history consistency could not be verified.
- Android `:app:assembleDebug` passed. `adb devices` was empty, so physical IME, Back, notification picker, system bars and TalkBack remain `NOT EXECUTED`.
- A deterministic Asia/Shanghai timezone-boundary fixture passes; live account/staging timezone behavior remains unverified. No API schema, database, Agent, Planner, or HITL policy changed. No commit, push, merge, production deployment, or tag was performed.
- No API schema, database, Agent, Planner, or HITL policy changes were made. No commit, push, merge, production deployment, or tag was performed.
