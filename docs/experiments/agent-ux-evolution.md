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
| Modify agent plan | Planning edit/lock controls or another chat prompt | No common visual plan artifact/edit path surfaced across views. |
| Apply plan | Validate → read status/version → apply | Manual validation duplicates deterministic apply revalidation and adds a technical step. |
| HITL | Inline ApprovalCard or Approvals inbox → inspect details → approve/edit/reject | Payload is prominent; timezone inconsistencies and recurring preview fallback undermine trust. |
| Replan | Planning local-replan tab → specify blocked interval/horizon/tasks → preview → apply | User must understand disruption mechanics and raw reason codes. |
| Insight | Insights list → generic action / Chat deep link | Chat prefills a prompt containing an insight ID; user must send it again. |
| Notification deep link | Notification → route target where available | E2E coverage exists for notification paths; action context should be verified per destination. |
| Briefing | Briefings → choose date/generate/view | Separate workspace; continuation into Chat should preserve context and avoid re-entry. |
| Error/retry | Error message → user interprets request ID/backend details → retry | Chat and notification surfaces risk leaking internal details; recovery affordance consistency is unclear. |

## 3. Current Frontend Problems

Planning, Approval, Chat progress, Today empty-state actions, and user-facing notification errors received a first implementation pass. Today and mobile navigation foundations remain. APIs remain the authority for business outcomes; no frontend scheduling, recurrence, conflict, or risk rules were added.

## 4. Agent Interaction Problems

Current Chat has SSE events and tool records, but uses tool names as the default activity language. Structured artifact references are not yet demonstrated in the inspected response contract. Insight-to-chat carries a prompt string and ID through query parameters rather than launching a structured action.

## 5. Information Architecture

Desktop currently exposes Today, Chat, Calendar, Briefings, Insights, Approvals, plus settings. Mobile uses Today, Chat, Calendar, More. Preserve all routes and first reduce cognitive load within Planning/Chat/Approval; navigation regrouping should follow usage evidence rather than hiding important pending decisions.

## 6. Planning UX Redesign

Implemented first step: Planning opens with a goal prompt that routes the user's text into Chat, and the task-selection/API-shaped workflow is behind “高级规划设置”. A reusable `PlanPreview` now renders a timezone-aware timeline and unplaced work. Advanced details expose per-task lock/regenerate controls. Normal users apply once; apply still relies on server-side deterministic revalidation. Limitation: this frontend currently cannot show backend-authored `display_reason`, key tradeoffs, or a structured before/after edit; it uses a generic unplaced explanation and Chat still requires the user to send the prefilled goal.

## 7. Chat UX Redesign

Implemented first step: progress summaries use user-facing activity labels with the raw tool trace collapsed; run and transport failures use recoverable user language. Goal and Today actions can prefill Chat. Structured plan artifacts still need authoritative references before they can be rendered in Chat/Today/Insight/Approval.

## 8. Approval UX

Keep the inbox and inline approval surfaces backed by the same card and state. The card now leads with a change summary, folds raw request/parameters, removes client-generated recurring occurrences, renders backend `display_context.occurrences` only, and formats/edits business datetimes in the preference IANA timezone. When the backend omits occurrence previews it shows a count and says dates are unavailable.

## 9. Today UX

Preserve next action and timeline. The empty-day mobile action now offers “帮我安排今天” and routes the goal to Chat; direct CRUD links remain secondary. Further state-aware actions need authoritative Today signals and still need journey evaluation.

## 10. Insight / Notification / Briefing UX

Insights now use account timezone for deadline evidence and specific CTA labels for capacity/deadline/overdue risks; the Chat handoff still makes users send a prefilled prompt. Notification settings now use user language for backend push availability, hide delivery codes in technical details, and use generic errors. Briefing journeys were not redesigned in this pass and need follow-up evaluation.

## 11. Timezone Audit

Fixed the audited Planning range/blocked inputs and plan timestamps, Approval editing/occurrences/proposal timestamps, and Insight due-time evidence using shared timezone utilities and the account IANA preference. An E2E scenario runs a Europe/London browser with Asia/Shanghai account preference and checks the resulting UTC range. Task, Event, and Reminder editors already use account-timezone utilities. The second iteration now detects local times skipped or repeated by DST transitions across Event, Task, Reminder, Approval edits, and Planning ranges. Skipped times and repeated times are rejected with an explanation; selecting the first versus second instance of a repeated hour is not yet supported. UTC timestamps used only for storage/API transport are not display defects.

## 12. Error UX

Chat no longer renders run exception text/request IDs in its normal error path. Notification settings now show recoverable text, human channel labels, and fold failure codes into technical details. More API failure cases and native permission errors still need review.

## 13. Mobile / Android

Existing evidence includes mobile navigation and keyboard-aware Chat tests plus mobile E2E specs. Continue using responsive layout and safe-area behavior; the new plan/approval views must remain usable at 320–430px and avoid horizontal overflow.

## 14. Accessibility

Existing interactive flows have labels in several areas. Remaining verification needed: keyboard walkthrough of Plan/Approval, semantic progress announcements, focus behavior for expanded technical details, and small-screen touch targets. No accessibility pass is claimed without execution evidence.

## 15. Before / After Metrics

No baseline interaction telemetry or recorded User Simulator/Blind Judge artifacts were found in the inspected frontend test tree. Metrics are therefore marked **not measured** until browser journeys are executed. Structural before/after comparison for the primary Planning path:

**Before:** open Planning → select tasks → set date range → choose ordering → choose strategy → generate → inspect raw status/version/reasons → validate → apply.

**After target:** state a goal in Chat or choose a day/week preset → inspect a readable plan and unplaced explanations → adjust in natural language → apply once. A backend HITL proposal remains required when policy demands it.

Turns, clicks, time-to-first-useful-UI, clarification rate, acceptance, and completion time: **not measured** in this audit.

## 16. Playwright Journey Results

Playwright mock UI run: desktop workspace 6 scenarios and mobile workspace 13 scenarios were exercised. The day-plan path reached apply after opening Advanced Planning, generating the draft, and applying it (3 clicks); it also checked 320/375/430/1280px widths, zero horizontal overflow, and absence of raw status/version/strategy/reason fields. The locale test used Europe/London browser timezone with Asia/Shanghai account timezone and verified the submitted UTC range. The mobile approval card showed its change preview and primary action with no horizontal overflow. A selector mistake caused the first combined run of the natural-language entry test to time out; after correcting the selector, that scenario passed in isolation. These are mocked UI journeys, not a live backend or AgentRun completion test.

## 17. Blind UX Evaluation

No blind evaluation was run. Requires paired baseline/candidate captures and a task-based rubric covering completion, clarity, interaction cost, control, trust, recovery, accessibility, and visual hierarchy.

## 18. Failure Cases

Fixed in the first pass: browser/account timezone mismatch in Planning, Approval and Insight due evidence; client-invented recurring preview; Chat raw tool names as default progress; raw run errors in Chat; and provider jargon in notification availability. Fixed in the second pass: DST skipped/repeated local input is detected before writes, with form-level guidance and no partial Event+Task creation. Remaining: backend-authored unplaced explanations, the stale-plan user recovery path, choosing either occurrence during a repeated hour, structured plan artifact/edit, Insight→Chat auto-submit, notification actionability, briefing continuation, and accessibility screen-reader testing.

## 19. Remaining Limitations

This report records the required current-state journey map and two UX implementation rounds. The full request spans more journeys and asks for longitudinal, blind and multi-agent evaluation; this remains an incomplete product-wide UX evolution. No live backend, AgentRun completion, or baseline-vs-after satisfaction comparison was measured. API additions require regenerated OpenAPI/types and backend changes through application services.

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
