# TimeAgent V4 Release Validation / Product UX Evidence

Date: 2026-10-03
Branch: `codex/agent-ux-v3-interactive-loop`
Candidate commit: `32db32f`
Production deployment: out of scope; isolated staging only (`127.0.0.1:7081`).

## 1. Frozen feature scope

No Agent, Planner, Tool, Memory type, interaction type, large page, or animation was added. Work is limited to the three worst continuous-use findings (stale execution buckets, duplicate task surfaces, Day Closing recovery), the shared modal keyboard blocker, and plan-context navigation. Other ideas are in [the post-release backlog](v4-post-release-backlog.md).

## 2. Real Daily Loop result

The staging gate uses a real Chromium browser, the isolated staging frontend and backend, and the staging PostgreSQL database. It creates synthetic tasks through the UI, reads authoritative Task/Today/Plan/Event APIs, executes and completes a task, records “差不多” feedback, then creates a tomorrow draft through Day Closing. It intentionally drops the browser response after the real API has committed, retries with the same key, rejects a changed request under that key, changes selection to get a new key, reloads the draft, and checks that source task schedules/deadlines and events remain unchanged.

Result: **1/1 passed** on isolated staging at `127.0.0.1:7081` with a real Chromium browser, backend, and staging PostgreSQL. The journey created three tasks through the UI, verified their Today buckets against the real API, started/completed one, submitted Harvest feedback, created a tomorrow draft, simulated a committed request with a dropped browser response, retried with the same operation ID, rejected changed inputs under that ID, then changed selection, created a distinct draft, and reloaded to recover it. Task/event schedule facts remained unchanged; the new plans stayed drafts. No Apply or production write occurred.

Sanitized automated path counts: **11** page transitions, **19** clicks, **19** text inputs, **0** Agent turns, **0** tool calls, **0** clarifications, **0** approvals, **1** failed request (the intentionally aborted browser response after server commit), **1** HTTP error (the expected changed-request/idempotency rejection), and **1** recovery (same-key retry). These are scripted browser counts, not human effort or satisfaction measurements. Runner and gate: `frontend/tests/e2e/run-daily-loop-staging.ps1`, `frontend/playwright.daily-loop-staging.config.ts`, and `frontend/tests/e2e/live-daily-loop-staging.spec.ts`.

Los Angeles DST unit evidence covers local midnight on 2026-03-08: start `2026-03-08T08:00:00Z`, end `2026-03-09T07:00:00Z`. The existing Shanghai test covers UTC+8.

## 3. Real Agent results

The isolated staging real-Agent suite passed **2/2**: a plan-only priority reorder and a late calendar conflict rejected Apply, invalidated the draft, and preserved Task/Today facts. The separate staging interaction regression passed **1/1**, restoring its completion feedback after reload. The live Daily Loop journey is distinct from those Agent gates. The combined one-day Morning → Agent replan → conflict diff → HITL → afternoon → Day Closing journey has not been run as one continuous browser session.

## 4. Chat vs typed-interaction evaluation

The five matched scenarios and protocol are defined in [the V4 interaction evaluation plan](v4-chat-vs-interaction-evaluation.md). No human matched-pair run occurred in this validation turn. For priority, time movement, conflict, overload, and completion feedback, comparative completion correctness, turns, text inputs, structured interactions, clicks, clarifications, invalid actions, undo, recovery, preference, and decision time remain **unmeasured**. Scripted browser event counts are automated-path evidence and are not human effort or satisfaction measurements.

## 5. Appropriate Interaction evaluation

The existing real-Agent priority regression proves that an explicitly requested Priority UI can be opened and saved; it does not test whether the Agent independently chooses the right interaction. No valid denominator exists for `unnecessary_interaction`, `missing_interaction`, `wrong_interaction`, or `duplicate_interaction`; Appropriate Interaction Rate is **unmeasured**. The expected interaction-selection matrix remains a hypothesis in the evaluation plan.

## 6. Accessibility

Automated Drawer coverage now verifies focus entry, Tab/Shift+Tab containment, Escape close, and trigger focus restoration. Existing frontend tests cover the completion feedback and approval states. The shared Drawer fix removes the reviewed P1 modal keyboard blocker.

Physical NVDA/Chrome, VoiceOver/Safari, and TalkBack/Android sessions were **not executed**. The remaining keyboard/focus and live-announcement items are documented in the backlog; no physical assistive-technology conformance claim is made.

## 7. Android / mobile

Playwright mobile Chromium coverage remains synthetic browser evidence. `adb` is installed, but `adb devices -l` returned no connected device and no Android emulator command/device was available. Android WebView, virtual keyboard occlusion, drag-vs-scroll, back navigation, and physical touch target validation are **not executed**.

## 8. Failure cases and recovery

- Day Closing preserves the selected task IDs, request fingerprint, operation ID, and draft ID in tab-scoped `sessionStorage`; it stores no task names or user text.
- A same-selection retry reuses the operation ID. A changed selection clears it and creates a new operation ID.
- A draft reload fetches the saved plan from the authenticated Plan API; only a current `draft` is restored.
- Backend regression coverage rejects a changed request reusing an operation ID. The real staging gate repeats that check.
- The local user-facing staging runner checks `/health/live` and pins `TIME_AGENT_E2E_BASE_URL` and Playwright `baseURL` to `http://127.0.0.1:7081`; it never points at production.

## 9. Independent critic findings

Read-only critics identified: stale Now/Next/Later buckets (P1), duplicate Today task cards and completion controls (P1), missing Day Closing reload recovery (P1), missing real Daily Loop backend gate (P1), missing Day Closing DST coverage (P2), and a shared modal with no focus management (P1). UX review also found missing Today → Chat entity context and a one-way Planning → Chat handoff; the former now passes task/event IDs and context, and Chat plan cards now link back to `/planning?plan_id=…`.

The staging run also exposed a nested responsive-layout defect: at a 1280px desktop viewport, the Today execution panel switched to three columns inside a narrow content column, leaving task titles with no usable width. The three-column threshold now starts at `2xl`. The account had older synthetic completion-feedback items, so the browser gate now scopes Harvest to the task created by that run instead of whichever pending card was already first. Feedback state synchronization also ignores older interaction versions; a component regression covers a stale parent rerender.

Remaining P2s include keyboard focus after Timeline edits, ConflictResolver announcements, recurrence navigation announcements, small touch targets, Morning Brief retry affordance, and physical device validation. Findings, trigger steps, user consequences, and dispositions are in [the backlog](v4-post-release-backlog.md).

## 10. Changes after evaluation

- Today refreshes from server data at the next schedule boundary, on reconnect, and on window focus. It does not recalculate business buckets in the browser.
- Removed the duplicate legacy desktop/mobile task lists so Now/Next/Later is the primary task execution surface.
- Day Closing restores the same selection and draft after reload, and preserves idempotency across ambiguous responses.
- Drawer manages modal focus and Escape; regression test covers keyboard close and restoration.
- Today task/event Chat links carry the selected entity and guardrails; Chat plan previews link back to the same Planning draft.
- Added a staging-only real backend Daily Loop Playwright gate and a Los Angeles DST test.
- Delayed the Today execution three-column breakpoint to `2xl` after staging exposed zero-width task titles at 1280px.
- Preserve the newest completion-interaction version when a parent rerenders with stale data; added a targeted regression.

## 11. Automated and backend validation

- Frontend unit/component suite: **174 passed** in 36 files.
- Frontend lint and production build: passed. Build still reports a 600.40 kB minified / 184.38 kB gzip entry chunk.
- Desktop/mobile Playwright suite: **63 passed, 10 skipped**. Six tests requiring live-backend credentials were gated in the generic run; three dedicated staging suites passed (Daily Loop 1/1, Agent interaction 2/2, completion interaction 1/1). Four pointer/touch variants were skipped for the incompatible browser project.
- Real staging browser gates: Daily Loop **1/1**, Agent interaction **2/2**, existing interaction/reload **1/1**.
- Backend suite from this validation cycle: **697 passed, 3 skipped, 1 warning**; `ruff check` and Django system check passed. Staging `makemigrations --check --dry-run` reported no changes, and the staging health endpoint returned HTTP 200.
- `ruff format --check apps tests` still reports 37 existing, unmodified files that would be reformatted. No backend Python files changed in this validation turn.

## 12. Mypy status

`uv run mypy . --no-error-summary`: **30 findings across the same 7 existing files**. No Python production file was modified in this validation pass. See [mypy baseline](mypy-baseline.md) for classification; no broad casts or ignores were added.

## 13. Bundle status

The production build succeeds but reports a **600.40 kB minified / 184.38 kB gzip** entry chunk, above the 500 kB warning threshold. A chunk-level report is in [V4 bundle analysis](v4-bundle-analysis.md). Calendar and chat markdown code are already split into lazy chunks; the target of a main entry below 500 kB was not met. No new dependency was added solely for analysis.

## 14. Known limitations

- Human matched UX study and one-full-workday dogfood evidence are still outstanding.
- The one-day Agent-driven full journey was not run as one continuous session; prior separate real-Agent plan/reorder and Apply-rejection gates remain evidence only for those bounded paths.
- Physical screen reader and Android WebView/device validation were not available; automated Playwright mobile is not device conformance evidence.
- Main entry remains above the bundle warning threshold.
- 30 pre-existing mypy findings remain.
- Production was not deployed, tagged, or modified.

## 15. Release recommendation

**READY_WITH_KNOWN_LIMITATIONS** — the automated and staging gates pass. The continuous one-day human/Agent journey, matched human UX study, physical assistive technology and Android checks remain outstanding. Bundle size and the pre-existing type/format baselines also remain open. This is a merge recommendation only; the feature branch is pushed separately, with no merge, tag, or production deployment.
