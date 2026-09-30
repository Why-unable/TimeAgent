# TimeAgent Agent UX Evolution

## 1. Current UX Audit

Audit source: the current `codex/harness-hardening-v2` frontend, API contracts, and existing frontend tests/E2E specs on 2026-09-29. This is a code-based baseline; the Playwright scenarios below are not represented as executed until a real run is recorded.

Strengths to preserve: Today is the authenticated landing page; Chat supports SSE recovery and conversation history; approvals can appear inline and in a separate inbox; mobile has bottom navigation and keyboard-aware behavior; Today has a timeline/next action; Insights have deep links; onboarding and generated API types exist.

Primary observed UX risks:

- Planning defaults to a planner console: task ID selection, algorithm ordering, strategy, compare, validate, and raw lifecycle/version/expiry/reason values compete with the plan outcome.
- Planning date inputs and plan displays use the device timezone in several paths, despite a shared IANA timezone utility and user preference hook.
- Approval recurrence fallback calculates occurrences in the browser, and approval date editing/display uses browser timezone.
- Chat's tool activity panel displays raw tool names, and failed runs may show backend exception text plus request ID.
- Desktop exposes six workspace destinations, while mobile already progressively hides secondary areas.
- Notification settings and diagnostics expose provider vocabulary and failure codes in normal content.
- Unplaced plan items render raw reason codes; Today quick actions are mostly CRUD shortcuts rather than state-aware assistant tasks.

## 2. Current UX Journey Map

| Journey | Current path | Friction / trust risk |
| --- | --- | --- |
| First visit | Login/guest → onboarding → Today | Onboarding exists; first useful action still depends on recognizing the assistant/navigation. |
| View today | Today → next action, timeline, counts, quick actions | Strong base; quick actions are static and count-oriented sections can compete with next action. |
| Ask about today's schedule | Chat → empty-state prompt → send → tool activity → answer | Raw tool names are exposed; first useful progress is not semantic. |
| Ask agent to plan tasks | Chat prompt or Planning → select task IDs/range/ordering/strategy → generate | Planning is API-shaped; ordinary route requires several decisions. |
| Modify agent plan | Planning edit/lock controls or another chat prompt | Chat now renders a schedule-plan artifact and can refresh it from a newer plan reference; a live natural-language edit journey still needs evaluation. |
| Apply plan | Validate → read status/version → apply | Manual validation duplicates deterministic apply revalidation and adds a technical step. |
| HITL | Inline ApprovalCard or Approvals inbox → inspect details → approve/edit/reject | Payload is prominent; timezone inconsistencies and recurring preview fallback undermine trust. |
| Replan | Planning local-replan tab → specify blocked interval/horizon/tasks → preview → apply | User must understand disruption mechanics and raw reason codes. |
| Insight | Insights list → primary action / Chat handoff | The Chat handoff now starts the selected insight request directly; the Agent still receives the insight ID as context. |
| Notification deep link | Notification → route target where available | E2E coverage exists for notification paths; action context should be verified per destination. |
| Briefing | Briefings → choose date/generate/view | Separate workspace; continuation into Chat should preserve context and avoid re-entry. |
| Error/retry | Error message → user interprets request ID/backend details → retry | Chat and notification surfaces risk leaking internal details; recovery affordance consistency is unclear. |

## 3. Current Frontend Problems

Planning, Approval, Chat progress, Today empty-state actions, and user-facing notification errors received a first implementation pass. Today and mobile navigation foundations remain. APIs remain the authority for business outcomes; no frontend scheduling, recurrence, conflict, or risk rules were added.

## 4. Agent Interaction Problems

Current Chat uses user-facing activity labels with raw tool traces folded away. It now receives reference-only schedule-plan artifact events and loads the plan through an authenticated, user-scoped detail API; conversation history retains those references. Other artifact types and other surfaces are not implemented yet. Insight-to-chat still carries the selected ID in prompt context, but its explicit CTA now starts the request directly.

## 5. Information Architecture

Desktop currently exposes Today, Chat, Calendar, Briefings, Insights, Approvals, plus settings. Mobile uses Today, Chat, Calendar, More. Preserve all routes and first reduce cognitive load within Planning/Chat/Approval; navigation regrouping should follow usage evidence rather than hiding important pending decisions.

## 6. Planning UX Redesign

Implemented first step: Planning opens with a goal prompt that routes the user's text into Chat, and the task-selection/API-shaped workflow is behind “高级规划设置”. A reusable `PlanPreview` now renders a timezone-aware timeline and unplaced work. Advanced details expose per-task lock/regenerate controls. Normal users apply once; apply still relies on server-side deterministic revalidation. The natural-language goal CTA now starts the Chat request directly. Limitation: this frontend currently cannot show backend-authored `display_reason`, key tradeoffs, or a structured before/after edit; it uses a generic unplaced explanation.

## 7. Chat UX Redesign

Implemented first step: progress summaries use user-facing activity labels with the raw tool trace collapsed; run and transport failures use recoverable user language. Planning, empty Today, and Insight CTAs explicitly launch their request once. Ordinary `?prompt=` links remain editable prefill, and a failed launch restores the text to the composer. Schedule-plan references from Agent events are rendered as the shared timezone-aware `PlanPreview` in Chat and are reloaded when a later version is emitted. The artifact card keeps application behind the existing confirmation flow.

## 8. Approval UX

Keep the inbox and inline approval surfaces backed by the same card and state. The card now leads with a change summary, folds raw request/parameters, removes client-generated recurring occurrences, renders backend `display_context.occurrences` only, and formats/edits business datetimes in the preference IANA timezone. When the backend omits occurrence previews it shows a count and says dates are unavailable.

## 9. Today UX

Preserve next action and timeline. The empty-day mobile action now offers “帮我安排今天” and sends that goal to Chat in one tap; direct CRUD links remain secondary. Further state-aware actions need authoritative Today signals and still need journey evaluation.

## 10. Insight / Notification / Briefing UX

Insights now use account timezone for deadline evidence and specific CTA labels for capacity/deadline/overdue risks; “问助理” starts a single Chat request with the selected insight ID and title in its prompt context. Notification settings now use user language for backend push availability, hide delivery codes in technical details, and use generic errors. Briefing journeys were not redesigned in this pass and need follow-up evaluation.

## 11. Timezone Audit

Fixed the audited Planning range/blocked inputs and plan timestamps, Approval editing/occurrences/proposal timestamps, and Insight due-time evidence using shared timezone utilities and the account IANA preference. An E2E scenario runs a Europe/London browser with Asia/Shanghai account preference and checks the resulting UTC range. Task, Event, and Reminder editors already use account-timezone utilities. The second iteration now detects local times skipped or repeated by DST transitions across Event, Task, Reminder, Approval edits, and Planning ranges. Skipped times and repeated times are rejected with an explanation; selecting the first versus second instance of a repeated hour is not yet supported. UTC timestamps used only for storage/API transport are not display defects.

## 12. Error UX

Chat no longer renders run exception text/request IDs in its normal error path. Notification settings now show recoverable text, human channel labels, and fold failure codes into technical details. More API failure cases and native permission errors still need review.

## 13. Mobile / Android

Existing evidence includes mobile navigation and keyboard-aware Chat tests plus mobile E2E specs. Continue using responsive layout and safe-area behavior; the new plan/approval views must remain usable at 320–430px and avoid horizontal overflow.

## 14. Accessibility

Existing interactive flows have labels in several areas. Remaining verification needed: keyboard walkthrough of Plan/Approval, semantic progress announcements, focus behavior for expanded technical details, and small-screen touch targets. No accessibility pass is claimed without execution evidence.

## 15. Before / After Metrics

The account-entry evaluation in Checkpoints A-C added current-source browser observations, three independent simulator runs, a fresh holdout task, and a blind screenshot comparison. Satisfaction distributions and product-wide failure/abandon rates remain **not measured**; the observed entry journeys are too few and non-comparable to generalize. See `docs/experiments/agent-ux-evaluation/interaction_metrics.json`. Structural before/after comparison for the primary Planning path:

**Before:** open Planning → select tasks → set date range → choose ordering → choose strategy → generate → inspect raw status/version/reasons → validate → apply.

**After target:** state a goal in Chat or choose a day/week preset → inspect a readable plan and unplaced explanations → adjust in natural language → apply once. A backend HITL proposal remains required when policy demands it.

For the Planning path, turns, clarification rate, acceptance, and completion time remain **not measured** in this audit.

## 16. Playwright Journey Results

Playwright mock UI run: the earlier focused suite passed 7 desktop and 13 mobile scenarios. It verifies one-tap Planning submission, reload of a persisted schedule-plan reference into the Chat timeline, mobile keyboard/layout behavior, 320/375/430/1280px widths, zero horizontal overflow, and the existing apply flow. The locale scenario uses a Europe/London browser with Asia/Shanghai account timezone and verifies the submitted UTC range. The auth-entry follow-up has current-source browser evidence against a local Django backend and targeted auth E2E coverage. After updating stale smoke interactions and fixtures to the current UI, the full smoke suite passed 17/17. Mocked UI journeys do not establish a live AgentRun completion or acceptance test.

## 17. Blind UX Evaluation

Checkpoint C ran a blind screenshot comparison on a fresh no-account demo goal. The judge preferred X (high confidence): the reconstructed baseline advertised the requested guest experience, while the candidate showed only account registration. Both outcomes failed to provide the requested demo. After judging, X was disclosed as a controlled reconstruction with guest access forced visible and the actual disabled-backend error; Y was the current-source candidate driven by `guest_access_enabled=false`. The result does not show a task-completion win for either version. This comparison is limited to screenshots; it was not an interactive test. See `before_after_pairwise.json`.

## 18. Failure Cases

Fixed in the first pass: browser/account timezone mismatch in Planning, Approval and Insight due evidence; client-invented recurring preview; Chat raw tool names as default progress; raw run errors in Chat; and provider jargon in notification availability. Fixed in the second pass: DST skipped/repeated local input is detected before writes, with form-level guidance and no partial Event+Task creation. Fixed in the third pass: explicit Planning, Today, and Insight actions submit once while ordinary prompt links remain prefilled drafts. Fixed in the fourth pass: schedule-plan artifact references persist with conversations and render in Chat from an authenticated plan read. The auth-entry follow-up now reflects backend capability flags and repairs keyboard and retry usability. This approval iteration also fixes conflict context loss by showing the event, occupied interval, and exact backend-computed overlap. Remaining: the no-account demo holdout, backend-authored unplaced explanations, the stale-plan user recovery path, choosing either occurrence during a repeated hour, live natural-language edit evaluation, artifact surfaces beyond Chat, notification actionability, briefing continuation, and screen-reader testing.

## 19. Remaining Limitations

This report records the current-state journey map, four earlier UX implementation rounds, two approval-context iterations, and the A/B/C independent evaluation cycle for account entry. Two real model/Time Steward/tool harness cases were measured on isolated synthetic users: one created a candidate plan; another paused at a pending approval and was never resumed or applied. These are `Real AgentRun Verified` at harness scope only, not a browser-to-Apply user journey. The approval conflict UI is verified with mocked Playwright and backend service tests, but not with a live browser AgentRun. The product-wide UX evolution remains incomplete. API additions were made through a read-only backend view/serializer and OpenAPI plus frontend types were regenerated; the conflict metadata remains inside the existing display-context JSON contract and no migration was required.

## Checkpoints A-C: Account Entry Evaluation (2026-09-30)

- **Checkpoint A:** independent source UX, accessibility, scenario-generation, simulator, and experiment-analysis roles found that the current-source login page showed Guest while the real backend setting was false. The simulator clicked it once, received `游客体验当前未开放。`, and stopped. The Register tab was already visible; this was a misleading disabled CTA, not a page without any alternative. An initial raw 403 screenshot came from a bad local proxy Origin and is retained only as invalid-harness evidence.
- **Change A→B:** added `GET /api/v1/auth/options/` as a read-only projection of existing backend settings. The login page now shows only backend-enabled Guest/registration paths. If the options request fails, it hides Guest but keeps login and registration available with a retry; backend submission remains authoritative.
- **Checkpoint B:** an independent critic identified tab keyboard behavior, options-failure fallback, retry focus/target size, and English disabled-registration copy. Iterations added roving tab focus with arrow/Home/End behavior, localized server copy, an announced retry result, focus restoration, and a 44×44 CSS-pixel retry target. A critic retest verified the scoped findings; Playwright checked the 320px layout. This is not a whole-product accessibility pass.
- **Checkpoint C holdout:** a fresh simulator requested a fictional no-account demo. The current-source backend returned `guest_access_enabled=false`; the candidate correctly hid Guest, showed Registration, and did not enter personal data or submit prompts. The requested task did not complete, no schedule was written, and no AgentRun occurred.
- **Blind pair:** an independent judge, unaware of version mapping, preferred the reconstructed baseline screenshot because its Guest CTA matched the requested goal. It also saw the actual unavailable message. The candidate screenshot showed only registration. Neither completed the goal; calendar-free support was not established. Therefore no overall task-UX win is claimed. Capability-driven rendering is retained as a truthfulness/correctness fix, while no-account demo remains an unresolved product/configuration decision.
- **Automated measures:** current-source options response 200; auth entry ready in 195ms and registration form in 218ms; one click to open the form, zero personal data, zero chat requests. The small simulator set has no numeric satisfaction scores and is not representative.

## Final Validation Results (2026-09-30)

- Backend account tests: **25 passed**. `ruff check .` passed; changed backend files passed `ruff format --check`; Django system check reported no issues; migration check reported no changes.
- Frontend unit suite: **26 files / 128 tests passed**. ESLint and production build passed. The existing bundle warning remains: the main chunk is about 596 kB after minification.
- Playwright: auth-specific tests passed **3/3** and full smoke passed **17/17**. Earlier focused desktop/mobile workspace journeys passed **20/20**.
- OpenAPI regenerated with **0 errors** and the frontend schema types regenerated successfully. Schema generation emits one existing non-optimal `status` enum naming-collision warning. No database migration was created.
- Repository `git diff --check` passed. Only changed backend files were used for the formatter check; the repository-wide formatter has unrelated baseline files outside this change.

## Iteration 4 Before / After Record

- **Before:** a plan generated in Chat was only represented by Markdown/tool activity; after leaving the run, the conversation did not retain a renderable plan reference.
- **After:** completed planning tools emit a durable `schedule_plan` reference containing only plan ID and version. Conversation history exposes those references; Chat fetches plan details through the user-scoped Application Service endpoint and renders the shared `PlanPreview` in the account timezone. A later reference refreshes the same artifact. The card directs edits through Chat and leaves high-risk application behind the existing confirmation path.
- **Evidence:** backend tests cover artifact-event emission, conversation-history serialization, plan retrieval, and cross-user 404 isolation. Frontend tests cover persisted artifact loading. Desktop Playwright verifies the schedule timeline and status display. OpenAPI and generated frontend types were regenerated; no migration was required.
- **Interaction measure:** a user can inspect the plan in the same conversation without opening Planning or interpreting tool output. Natural-language changes, acceptance, and application completion were not measured with a live Agent.
- **Validation:** backend focused suite passed (47 tests); Django system check, migration check, Ruff, and formatting checks passed. Frontend unit suite passed (26 files / 122 tests), lint and build passed, and focused desktop/mobile Playwright passed 20/20. The existing production bundle warning remains (>500 kB main chunk).

## Iteration 3 Before / After Record

- **Before:** Planning, empty Today, and Insight actions navigated to Chat with a prefilled composer, requiring a second Send action.
- **After:** those explicit in-app actions carry a one-shot launch marker and send the intended prompt on arrival. Direct `?prompt=` links without that marker continue to prefill an editable draft. Failed sends restore the text so the user can retry; server-side high-risk approval policy is unchanged.
- **Evidence:** Chat unit tests verify an Insight launch posts exactly once and a plain prompt does not post. Insights tests verify its CTA carries the launch marker. Today tests verify its action URL. Desktop Playwright verifies Planning posts the entered goal; the focused desktop/mobile workspace suite passed 19/19.
- **Interaction measure:** the three entry actions now need one tap to issue the request instead of two. This counts initiation only; response latency, plan usefulness, completion, and acceptance were not measured.
- **Validation:** frontend lint and production build passed; final frontend unit tests passed (26 files / 121 tests). The unfiltered E2E run was interrupted after backend-dependent smoke tests timed out because the configured API proxy refused the local backend connection; the focused desktop/mobile suite passed 19/19. Django system check passed. `makemigrations --check --dry-run` produced no output and was interrupted after waiting over two minutes for the local database.

## Approval Conflict Context Iteration (2026-09-30)

### Before / after

**Before:** an approval card said only that there were *N* conflicts. After the first scoped pass it named the event and showed its occupied interval, but users still had to calculate the intersection themselves.

**After:** the backend event and action-proposal services provide `overlap_start_at` and `overlap_end_at`. The card shows the event title, its occupied interval, and the exact overlap in the account timezone. The frontend only displays the supplied interval; it does not compute conflict semantics. When overlap fields are absent, the card does not invent them. The copy asks the user to inspect and decide, and states that the action will not execute before confirmation; the existing explicit HITL controls remain.

### Independent evaluation

- **Iteration 1 blind comparison:** the judge preferred event title + occupied-time context over count-only context (confidence 0.98). The remaining failure was that users had to infer the intersection.
- **Iteration 2 blind comparison:** with the same proposal/layout/copy, the judge preferred X, which states `2026/10/01 15:30–16:00`, over Y, which shows only `15:30–16:30` (confidence 0.99). X scored 5/5 for task completion and clarity; Y scored 4/5 and 3/5 respectively. The byte-distinct neutral pair and mapping are in `approval_conflict_pairwise.json` and `blind-pair-approval/iteration-2/`.
- **User simulation:** an independent static simulator marked the single-conflict goal complete with satisfaction 4/5. It read “客户评审”, occupied time `15:30–16:30`, exact overlap `15:30–16:00`, and the no-execution-before-confirmation message. Clicks, turns, time-to-completion, and page transitions were not measurable from screenshots. A separate four-conflict fixture remains for disclosure regression and is not counted as the primary scenario.
- **Adversarial review:** no high-severity blocker. It noted that fixed navigation overlays some lower content in the captured viewport and that the displayed year adds length. The focused Playwright journey confirms the approval button can be scrolled fully above the navigation.
- **Accessibility review:** the final screenshot review found the 320px and 390px conflict details readable, with visible focus evidence on the disclosure and no color-only warning. Source-token contrast calculations are 9.46:1 for secondary card labels and 6.78:1 for inactive mobile navigation. Playwright presses Enter to expand the remaining conflict, verifies no 320px horizontal overflow, and checks approval-button reachability after scrolling. Screen-reader behavior, full manual keyboard use, and touch targets remain unverified.
- **Experiment Analyst:** the largest remaining scoped concern is that the fixed navigation covers lower card content in a static viewport, although Playwright confirms the approval button is reachable after scrolling. The next experiment is a real browser journey from an isolated AgentRun to a pending proposal, plus a manual screen-reader/full keyboard walkthrough; it must leave the proposal pending and never auto-approve. See `approval_conflict_iteration_analysis.json`.

### Validation and limits

- Frontend: 26 unit-test files / 131 tests passed; ESLint passed; production build passed with the existing ~596 kB main-chunk warning. The full smoke suite passed 19/19, and the two approval scenarios passed again after the final decision copy change.
- Backend: 628 passed, 3 skipped; 26 focused event/action-proposal tests passed; Ruff, changed-file formatting, Django system check, and migration check passed. OpenAPI generation had zero errors and the generated frontend schema had no diff because `display_context` remains an opaque JSON field. No migration was needed.
- The screenshots and Playwright calls use fixture data and intercepted API requests. No approval button was clicked; no real AgentRun was resumed, applied, or propagated to Today/Calendar. The full browser → live AgentRun → HITL → apply → Today journey is still **NOT VERIFIED**.
- The screenshot simulator and judge are not participant studies. No aggregate satisfaction, click reduction, turn reduction, approval completion time, or task success rate is claimed.

## Approval Decision Safety and Mobile Editing Iteration 3 (2026-09-30)

### Before / after

**Before:** a proposal could be approved after a stale or incomplete refreshed review, an edited operation could still carry display-only fields into a strict tool schema, and a conflict discovered during edit did not always leave a useful pending editor state. On mobile, reminder-target data could arrive after the initial focus attempt, and a closing soft keyboard could leave navigation hidden while the input remained focused.

**After:** approval and edit refresh current review/conflict state before changing the proposal. Incomplete review or a fresh conflict stores the updated review context/version and keeps the proposal pending; an edited payload is not applied. Conflict cards do not offer approval. The editor strips display-only event fields before resuming the tool, blocks invalid time ranges, retains an existing reminder target while its option is absent/loading, and remains open when the server returns a still-pending proposal. Focus retries when target data becomes ready; mobile navigation tracks the visual viewport and restores when the keyboard closes.

### Independent evaluation

- **Blind comparison:** the independent judge preferred candidate X, which includes the exact `15:30–16:00` overlap, over context-only Y with confidence **0.78**. X scored 4.5/5 for task completion, clarity, and trust; Y scored 4/5, 3.8/5, and 3.8/5. Y scored slightly better on visible scroll/navigation framing (4/5 vs 3.5/5), while X was more decisive about the conflict. Screenshots and scoring are recorded in `approval_conflict_pairwise_iteration_3.json`.
- **Holdout simulation:** the simulator identified 客户评审 and the exact overlap and rated the experience **4/5**, but only after scrolling to the action controls. It did not interact with the live app; no clicks or completion time were measured.
- **Adversarial review:** the earlier review found asynchronous reminder-target focus loss and an editor that closed when an incomplete review stayed pending; both were fixed. A later pass found two additional P2s: null times in legacy partial `update_event` previews and approval against a stale event `expected_version`. The preview now resolves null times to current values. Stale targets are refreshed in the pending proposal, visibly announced, and require another explicit decision; replaying the same decision key returns the pending result. The final recheck also verified that a `time: null` mutation displays its existing times while leaving unchanged values null on submit, and preserves the other endpoint when only one side changes. Regression coverage covers these cases. The read-only critic found no remaining reproducible scoped P1/P2; details are in `approval_conflict_critic_iteration_3.json`.
- **Accessibility review:** no new scoped P1/P2 was found after fixes. The review confirmed Enter opens the disclosure, the editor receives focus, cancel returns focus, and viewport restoration unhides/inactivates navigation correctly. The Playwright cancel path uses a click; real-device keyboard/screen-reader behavior remains unverified.
- **Experiment analyst:** evidence supports a scoped improvement in explaining the exact overlap and keeping the review pending until a safe decision. It does not support real-user or product-wide claims. The next evaluation should use an isolated live AgentRun that remains pending, followed by a human mobile keyboard/screen-reader walkthrough. See `approval_conflict_iteration_analysis_3.json`.

### Validation and limits

- Backend: **638 passed, 3 skipped**; focused action-proposal suite **24/24**. Ruff check and changed-file format check passed; Django system check reported no issues. Migration check reported no model changes, but its database-history check timed out against localhost PostgreSQL (port 5432).
- Frontend: **26 files / 143 tests passed**; ESLint and production build passed. The existing main chunk remains about 596 kB after minification.
- Playwright: the complete smoke file passed **20/20** after the final review-notice and expected-version editor assertions were added.
- No browser-to-live-AgentRun approval, apply, Today/Calendar propagation, human participant study, physical mobile-device run, or screen-reader walkthrough was performed. The holdout view still requires scrolling to reach its action controls. These results support the scoped interaction and safety changes; they do not establish product-wide UX improvement.

## Iteration 2 Before / After Record

- **Before:** the browser timezone conversion silently selected an instant when a user-entered local time fell into a DST gap or repeated hour.
- **After:** shared conversion classifies the local time using IANA rules and rejects nonexistent or ambiguous input before any write. Event, Task, Reminder, Approval edit, and Planning show a clear timezone-specific message. A linked Task is validated before it can be created as a side effect of creating an Event.
- **Evidence:** component tests cover a New York spring-forward gap, a New York repeated hour, and Lord Howe's 30-minute repeated interval. Event, Task, Reminder, Approval, and Planning tests assert that the invalid entry is explained and the write is blocked.
- **Remaining:** users cannot select which occurrence they mean during a repeated hour; they must choose another local time. The current test coverage uses mocked APIs and does not replace backend timezone validation.
- **Validation:** lint passed; 26 frontend test files / 119 tests passed; desktop/mobile Playwright passed 19/19; production build passed with the existing >500 kB main-chunk warning (594 kB). Django system check passed. Migration check did not return within two minutes while waiting on the local database and was interrupted; no backend files or migrations changed.

## Iteration 1 Before / After Record

- **Before Planning (code baseline):** select tasks → manually configure range/order/strategy → generate → inspect raw lifecycle → manually validate → apply.
- **After Planning (implemented):** enter a goal and choose “让助理安排” to prefill Chat; or open “高级规划设置” for deterministic planner controls. In the mocked apply journey, the direct advanced path took 3 clicks after page entry (open advanced, generate, apply); basic path was verified through prompt prefill only, not Agent completion.
- **Before empty Today:** static create-event/create-task/ask-assistant links.
- **After empty Today:** primary “帮我安排今天” goal with secondary CRUD links.
- **Interaction metrics:** no instrumented baseline; turns, clarification count, latency, time-to-useful-plan, and acceptance rate remain **not measured**. The 3-click result is a Playwright mock scenario count, not a comparative improvement claim.
