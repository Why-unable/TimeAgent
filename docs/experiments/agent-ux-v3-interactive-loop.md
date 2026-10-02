# Agent UX V3 — Interactive Planning & Execution Loop

**Status:** Iteration 1 implementation and paired evaluation completed; UX improvement not demonstrated
**Baseline checkout:** `06727f92e156baaee425cfce6fe5652d46a77858` on `codex/agent-ux-v3-interactive-loop`
**Scope:** Interactive draft planning and optional post-completion feedback. This is a new phase; it does not revise the V2 release boundary.

## UX audit

### Current Interaction Journey Map

| Journey | Current path | Current interaction | Gap for V3 |
|---|---|---|---|
| Plan from a goal | Chat request → Time Steward → `SchedulePlan` draft → typed interaction when requested → approval/apply | Draft is restored from run artifacts; a pending Agent-requested interaction opens its registered renderer | Direct ranking and timeline edits are structured, versioned draft actions |
| Plan from the planning page | Select tasks/range/order → create draft → choose a direct interaction → lock/unlock or regenerate → apply | Structured form plus deterministic schedule endpoints | Relative ranking is per-plan; advanced lock controls remain available |
| Review a high-risk action | Agent creates `ActionProposal` → `ApprovalCard` → approve/edit/reject → resume | Structured and versioned HITL | Keep this separate from low-risk draft manipulation; Apply remains behind its existing approval boundary |
| Complete today’s task | Today action → task completion endpoint → task state and completion signal → optional check-in | Completion remains one-step; a best-effort durable check-in is restored after completion | Feedback stays distinct from timer-derived duration evidence |
| Learn from execution | Started/resumed/paused/completed signals → duration evidence and recommendation services | Deterministic evidence; explicit memory/decision feedback APIs | Completion self-report is not currently captured or connected to later duration recommendations |
| Resolve a conflict or end the day | Chat explanation or manual task edits | Text-only or multi-page navigation | Candidate components are considered for a later round, not included automatically in Iteration 1 |

### Chat-only Frictions

- Before V3, changing a plan time or expressing its relative order required another natural-language turn.
- The chat plan artifact was durable, but there was no typed interaction lifecycle or pending recovery.
- Before V3, plan items had no separate explicit order contract; a plan-only reorder must never write permanent priority.
- Before V3, completion feedback was disconnected from the immediate complete action.
- Existing approvals are a distinct, useful interactive surface. V3 should reuse the accessibility patterns, not conflate ordinary edits with high-risk approval.

### Candidate Interactive Components

| Component | Decision supported | Proposed deterministic boundary | Priority |
|---|---|---|---:|
| `PriorityRanker` | Relative order within this draft | Versioned plan edit with explicit `ordered_task_ids`; does not update `Task.priority` | P0 |
| `InteractivePlanTimeline` | Move, resize, lock/unlock a draft item | Structured timestamps/lock values → planning application service → deterministic validation | P0 |
| `CompletionHarvest` / `CompletionCheckIn` | Optional fast/about-right/longer + optional reason | Task-linked, typed feedback; completion itself remains immediate | P0 |
| `ConflictResolver` | Choose a valid server-provided alternative | Only consume authoritative backend reason/candidate | P1, evaluate after first round |
| `PlanDiffReview` | Understand what changed | Render a diff computed from authoritative plan versions | P1, evaluate after first round |
| `OverloadDecision` / `TimePreferencePicker` | Resolve competing goals/preferences | Structured choice or explicit semantic request as appropriate | P2 |
| `DayClosing` | Carry unfinished work into tomorrow | Deterministic close summary then create next-day draft; never silently apply | P2 |
| `MemorySuggestion` / `InsightActionCard` | Approve durable learning or take action | Existing explicit Memory Policy/proposal path | P2 |

### Priority Ranking

1. **Interaction Artifact foundation:** authenticated ownership, typed payload, allowed-action validation, durable pending recovery, version checks, expiry, and idempotent submission history.
2. **`PriorityRanker`:** direct, plan-local order change, keyboard alternative, undo, and clear boundary from permanent task priority.
3. **`InteractivePlanTimeline`:** direct time/lock/estimated-duration manipulation with current backend constraints as authority, safe rollback on rejection, and readable feedback.
4. **`CompletionHarvest` / `CompletionCheckIn`:** keep the ordinary complete action primary and immediate; offer optional feedback afterward, without overstating self-report as measured duration.

### Implementation Sequence

1. Freeze this checkout and record the existing journeys and evaluation limits (this section).
2. Add the durable typed artifact and submission application-service boundary; document the new persistence decision in an ADR.
3. Add plan-local order and interactive draft controls; keep changes in `SchedulePlan` until the existing Apply/HITL boundary.
4. Add an optional task completion check-in and typed feedback persistence; leave existing completion behavior available in one action.
5. Run focused regression and independent UX/accessibility reviews, repair findings, then use a newly generated holdout whose prompts and expected outcomes were not available during implementation.
6. Only after first-round evidence, decide whether DayClosing or other P1/P2 components merit a second round.

## Architecture

Production stays **Single Time Steward → Tools → Deterministic Services**. The Time Steward can call `request_plan_interaction` with a plan id and one of two literal types. That tool calls `InteractionArtifactService`; it returns references, current versions, payload, and allowed actions. The chat surface fetches pending artifacts associated with that AgentRun and opens the matching renderer from the frontend registry. The Agent cannot provide UI markup. Manual planning-page entry points remain available.

For planning, `SchedulePlan` remains the source of truth for the draft. An interaction references the plan and the version it was created from; it does not duplicate mutable schedule state. Direct controls submit structured edits to a deterministic application service. `Task` records change only after the existing Apply boundary; high-risk agent-initiated Apply remains subject to `ActionProposal`/HITL.

For completion, `TaskExecutionSignal` remains evidence for measured active time. A user-selected duration category/reason is separately labelled self-reported feedback. Completion through the task state-change service creates or reconciles the optional pending check-in in a nested savepoint; a failure does not block completion, and replaying the completion request attempts reconciliation again. Any lasting preference change must use the existing explicit Time Memory/decision feedback policy path.

## Interaction Artifact Contract

The API contract must carry:

```text
interaction_id, conversation_id?, agent_run_id?, plan_id?, plan_version?,
type, payload, allowed_actions, status, expires_at, version
```

Submission contract:

```text
interaction_id, expected_version, action, values, idempotency_key
```

Initial allowlisted types are `priority_ranking`, `plan_timeline_edit`, `task_completion`, and the evidence-gated `memory_suggestion` subflow. Payload validation is type-specific and contains references/structured fields only. Pending artifacts must be fetchable after a reload. Every state-changing submission must be authorized against the current user, version-checked, idempotent, and routed through its application service. Interaction DOM or JSX does not belong in Agent messages.

## Component Registry

| Type | Renderer | State owner | First-round status |
|---|---|---|---|
| `priority_ranking` | `PriorityRanker` | versioned `SchedulePlan` order | Iteration 1; manual entry and Agent-requested |
| `plan_timeline_edit` | `InteractivePlanTimeline` | versioned `SchedulePlan` items | Iteration 1; manual entry and Agent-requested |
| `task_completion` | `CompletionHarvest` / `CompletionCheckIn` | completed Task plus typed feedback | Iteration 1 |
| `memory_suggestion` | `MemorySuggestionCard` | explicit duration feedback policy | Evidence-gated child of CompletionHarvest |
| `conflict_resolution` | `ConflictResolver` | backend candidate/result | Deferred |
| `day_close` | `DayClosing` | deterministic day summary and next-day draft | Deferred pending evaluation |

## Evaluation boundary and baseline

Existing results are context, not V3 before/after evidence:

- The planning harness report documents a curated scenario set and historical agent-vs-deterministic comparisons. The old ambiguity/replan cases were exposed during tuning; they are regression evidence, not a fresh V3 holdout.
- The V2 harness report records 30/30 real-agent diagnostic regressions and two blind judges over eight cases. Those are agent-planning/approval results, not direct-manipulation UX outcomes.
- The prior UX work has static critics, simulators, screenshots, and mocked browser journeys. Its own report says general satisfaction, planning turns, clarification rate, acceptance, and completion time were not measured. Some prior holdout artifacts are incomplete or already exposed and are not eligible as a fresh holdout.
- V2’s production Browser → Agent → Plan/Edit → HITL → Apply → Task/Today smoke is useful integration evidence; it is not a sample of user decision speed or preference.

Therefore no valid V3 baseline exists yet for decision time, typed-vs-text input count, plan acceptance after interaction, interaction abandonment, perceived plan-change clarity, or completion-feedback utility. These remain **unmeasured** until a matched independent run instruments them. Test/build pass alone will not be presented as UX success.

## Iteration 1

### Scope

Implement only the interaction foundation, plan-local ranking, direct draft timeline editing, and optional task completion feedback. Do not add DayClosing or other second-round components before first-round evaluation.

### Subagent Findings

- **Frontend audit:** PlanPreview is read-only; planning-page already supports lock/unlock and draft Apply; Today completion is one-step; task duration recommendations live elsewhere; no generic interaction registry/recovery or V3 telemetry was found.
- **Backend audit:** PlanningService already has versioned deterministic edits/validation and Apply delegates business writes through services. It lacks plan-order and structured failure candidates. Execution signals are immutable and idempotent; duration evidence is timer-derived, so check-in self-report must remain distinct.
- **Evaluation audit:** Existing evaluator roles are represented by static artifacts rather than a repeatable end-to-end V3 harness. Existing UX baselines do not measure decision time/input reduction and old sealed scenarios are no longer untouched. Fresh holdout generation and disclosure control are required.

### Results and open measurements

#### Implementation and regression evidence (2026-10-02)

- Backend: `uv run pytest` — **671 passed, 3 skipped**, one tokenizer fallback warning. Skips: the existing async interrupt limitation and two opt-in live notification tests.
- Frontend unit/component tests: `npm exec vitest run` — **30 files, 153 tests passed**.
- Browser interaction suite: `npm exec playwright test tests/e2e/interactive-planning.spec.ts -- --project=chromium --project=mobile-chromium` — **22 passed, 4 skipped**. The skips are project-specific pointer/touch combinations; supported mouse and touch cases each ran in their intended project. Tests use routed/mock APIs and do not verify a live Agent or production backend.
- Cross-run browser regression: a later run reopening an existing draft asynchronously displays the pending ranker, announces it through a polite live region, and leaves keyboard focus in the composer — **1 passed** in Chromium. This also verifies the chat history path; the later run’s artifact reference must be retained even when its plan version did not change.
- Static/build checks: `uv run ruff check .`, Ruff format check on changed Python files, Django system check, migration drift check, ESLint, and TypeScript/Vite build passed. Vite reports the existing main bundle at about 599 KB and the configured 500 KB warning threshold.
- OpenAPI and generated frontend types were regenerated for the Interaction API.
- The completion feedback retry test covers reload in the same browser session. Server-side best-effort creation plus replay of completion provides the durable recovery path; it is not a guarantee if both the original completion and all retries occur while the interaction store is unavailable.
- Live local staging regression: the isolated V3 stack at `127.0.0.1:7081` completed a real Chromium flow against its local backend — create a draft/task, open the timeline editor, complete the task, and verify the feedback interaction after reload — **1 passed**. This is local staging evidence, not production evidence.

#### Independent evaluation and repair

- The adversarial UX critic found a P1: a later AgentRun requesting an interaction for an existing draft could leave the card associated with the earlier run. `request_plan_interaction` now emits a schedule-plan artifact reference; live events and history retain the latest related run id, and an unchanged plan version no longer hides the request. Backend event and two-run frontend regressions pass. Independent source re-review found no remaining P1; a live SSE-specific frontend test remains a nonblocking coverage gap.
- A live staging attempt found that a request to find existing tasks by title and create a draft exposed task lookup but omitted the schedule-draft tools. Tool routing now recognizes explicit “create a plan/draft” language and keeps read-only task lookup available during planning while filtering task mutation tools; a focused routing regression passes.
- PostgreSQL staging returned an error when submitting a plan-ranking interaction because `SELECT FOR UPDATE` also targeted nullable joined rows. The interaction service now locks only its artifact row while retaining the shared schedule-write lock; the API regression verifies that ranking changes the draft order only.
- The accessibility critic found a P2: manual open/snooze could lose keyboard focus, and an asynchronous Agent open was not announced. Manual open now focuses the selected region, snooze returns focus to its matching selector, and automatic open uses a polite live announcement without moving focus. Independent review found no remaining confirmed issue. Browser assertions cover timeline focus/return and cross-run asynchronous announcement/focus preservation.
- Automated browser evidence does not certify VoiceOver, TalkBack, NVDA, physical touch, system zoom/high contrast, or Android virtual keyboard behavior.
- The Experiment Analyst found that telemetry records events but does not aggregate outcomes. `duration_ms` is not accepted by the interaction client for the allowlisted events; decision time remains unmeasured. Completion-feedback shown/submitted records lack a reliable join key, and timer-derived actual-vs-planned evidence remains separate from self-report. No user-improvement claim is supported by current evidence.
- An initial post-freeze candidate was excluded after its generator disclosed prior exposure to report sections. A separate isolated generator read only the pasted request and created a replacement; its prompts and expected outcomes remain sealed in the artifact and are not reproduced here.
- The first replacement run could not reach a user-facing page and yielded no observations. It was not treated as a product result. A later, fresh post-repair holdout was run through isolated local V3 and frozen-baseline browser stacks; results are summarized below.
- The independent critics found no evidence supporting a V3 user-improvement claim. They treated rough response times as descriptive only, separated visible chat claims from verified task writes, and excluded contaminated, incomplete, or blocked cases from outcome denominators.
- Second-round decision: do not add DayClosing or another P1/P2 component to Iteration 1. H07 was blocked because no DayClosing UI exists, so this replay provides no evidence about its usefulness; keep that work deferred to a separately scoped iteration.

#### Holdout Results

- An isolated generator created a new 9-case holdout from the original request after the repairs. Sealed file: `docs/experiments/artifacts/agent-ux-v3-repair-independent-holdout-2026-10-02.json`; SHA-256: `9eef4ae36dc27d98a815dae467f117e0046740c32358a021d2781c477668af3a`. Scenario prompts and expected outcomes are intentionally not copied into this report.
- The independent simulator used disposable synthetic accounts through the user-facing UI on isolated local V3 staging (`127.0.0.1:7081`) and a frozen V2 baseline (`127.0.0.1:7082`). It did not use APIs, repository internals, or production data. Chats were opened manually; this run did **not** exercise Agent-requested interaction cards.
- Case accounting: **5 fully observed matched pairs** (H01–H04, H09); **1 contaminated pair** (H05, shared carry-over task); **1 paired but incomplete** (H06, no visible active-timer state and no duration recorded); and **2 blocked before prompting** (H07, no visible day-close view; H08, no user-facing path to establish historical execution evidence).
- Across the five fully observed pairs, each condition used 9 natural-language turns in total. Each case had the same turn count on both sides. One case showed a displayed chat success state after confirmation, but Task/Today persistence was not checked; do not count it as a verified task write. One case had a paired Start action but no verified active timer or duration outcome.
- Two cases targeted times already in the past at the local test time; neither interface showed a warning. This observation does not establish whether a task write persisted. The service-level Apply validator separately rejects plan items whose start is before its injected current time; no conclusion about end-to-end persistence is made from this browser replay.
- The Blind Comparator found 5 matched cases with exercised clarification/recommendation outcomes and a separate confirmation-flow observation whose persistence was unverified. It observed content differences in two cases but could not rank them without prompts and expected outcomes. The independent measurement audit concluded that timing is too rough for a decision-speed comparison and that no UX improvement claim is supported.

#### Accessibility Results

- Manual interaction entry focuses the selected region; snoozing returns focus to the matching selector. Automated assertions cover both on the timeline path.
- A later AgentRun opening an existing plan is asynchronously announced via a polite live region while preserving the composer focus. This was verified in Chromium with mocked APIs.
- Priority ordering has keyboard alternatives and focus restoration; reduced-motion and 320/375/430 px responsive coverage exists in the automated suite. No VoiceOver, TalkBack, NVDA, physical-device touch, Android virtual keyboard, system zoom, or high-contrast evaluation was possible.

#### Real Browser Results

- Real Chromium and mobile Chromium browsers exercised direct plan controls against routed/mock APIs: **22 passed, 4 skipped** in the planning suite; a separate cross-run async open/focus-preservation case passed in Chromium.
- A separate real Chromium test exercised the repaired V3 UI against local staging and its real backend: **1 passed** for timeline restore and completion-feedback restore after reload.
- A real Chromium regression against isolated local staging used live AgentRuns to create a plan from tasks found by title, open the priority interaction in a later run, persist a plan-only reorder, and open the timeline interaction. Both a direct timeline edit and a later Agent-requested edit to a past time were rejected; the UI displayed “不能把任务安排在过去”, the Agent reply reported failure, and the plan version/item, fixture Task planned timestamps, and Today fixture schedule remained unchanged: **1 passed**. The service-level Apply validator also rejects past plan items; a real Agent-run claim after an Apply rejection was not tested.
- The paired holdout exercised both local builds through their UI, but only manually opened chat flows. It is not evidence for Agent-requested cards, and the confirmation-flow “executed” indicator was not followed by Task/Today verification. No production deployment or production browser test was performed for V3.

These results verify implementation contracts and simulated browser behavior only. They are not evidence that users decide faster, understand plan changes better, accept more plans, or find check-ins useful.

Implementation, focused regression, independent evaluation, repairs, accessibility verification, browser results, and the fresh holdout are recorded below. Keep numeric fields `unmeasured` unless evidence includes a defined denominator, method, and source artifact.

| Measure | Baseline | Iteration 1 | Evidence / caveat |
|---|---:|---:|---|
| Time to make plan decision | Unmeasured | Unmeasured | No prior instrumented user/simulator timer |
| Text turns / structured actions | Unmeasured | Unmeasured | Do not infer from component tests |
| Plan acceptance after interaction | Unmeasured | Unmeasured | Define numerator/denominator before run |
| Invalid-drop recovery and undo | Unmeasured | Unmeasured | Track event counts without user text |
| Completion feedback rate | Unmeasured | Unmeasured | Optional; report eligible completions as denominator |
| Actual-vs-planned ratio | Available only with execution signal evidence | Unmeasured | Timer-derived duration must be kept separate from self-report |
| Fresh holdout | None | 5/9 fully observed matched pairs; 1 contaminated, 1 incomplete, 2 blocked | Sealed file `docs/experiments/artifacts/agent-ux-v3-repair-independent-holdout-2026-10-02.json`; no prompt text included; no UX improvement claim supported |
| Accessibility / real browser | V2 smoke exists; V3 direct manipulation absent | Mocked Chromium/mobile browser suite plus 2 live local-staging Chromium regressions; paired UI replay completed | Real assistive technology, physical touch, system zoom/high contrast, and Android virtual keyboard remain unverified; paired replay did not exercise Agent-requested cards |

## Telemetry and privacy

Instrument allowlisted event types and counts: `interaction_shown`, `interaction_started`, `interaction_completed`, `interaction_abandoned`, `interaction_type`, `drag_count`, `invalid_drop_count`, `undo_count`, `plan_edit_count`, `plan_acceptance_after_interaction`, `completion_feedback_rate`, `actual_vs_planned_ratio`, `memory_suggestion_shown`, `memory_suggestion_accepted`, and `day_close_completion_rate`.

Do not send message text, task titles/descriptions, free-text reasons, credentials, or model-private reasoning. Reason choices are fixed enums. Do not report an event as anonymous if its stored record can identify a user; document the actual retention and identity boundary alongside the implementation.

The current telemetry table has no user/task/conversation foreign keys. That describes the event-row schema only; it does not prove end-to-end anonymity in the authenticated request, application logs, or retention path. The browser reports only allowlisted shown/started, invalid-drop, edit/undo, and memory-shown events; the backend owns completed/abandoned, post-interaction plan acceptance, memory acceptance, and completion feedback outcomes. The actual-vs-planned ratio is derived server-side from execution signals when feedback is submitted, and is omitted without usable timer evidence. A completion-feedback rate can only be interpreted against check-ins actually shown, not every task completion in the product. Browser-reported counts remain best-effort client telemetry, and interaction duration is not currently submitted; decision time is therefore unmeasured.

## Remaining Problems

- DayClosing and other second-round components remain deferred; the current holdout could not evaluate their utility.
- Validate on real assistive technology and mobile/touch devices; automated DOM assertions cannot certify screen-reader behavior.
- Verify the Agent’s reply against Task/Today when Apply itself rejects an invalid or past-time plan. The live browser regression covers a direct timeline rejection and an Agent-requested draft-edit refusal, with unchanged plan/Task/Today state, but does not exercise an Agent claim after Apply rejection.
- Measure whether direct interaction reduces decision time/input while preserving understanding and acceptance using an instrumented protocol with defined start/stop events, clean isolated fixtures, and expected-outcome scoring; the current replay cannot answer this.
- Measure whether direct interaction reduces decision time/input while preserving understanding and acceptance using an instrumented protocol with defined start/stop events, clean isolated fixtures, and expected-outcome scoring; the current replay cannot answer this.
- Verify if and how self-reported completion categories should influence future duration recommendations without confusing them with measured time.
- The simulator used synthetic local accounts, not real users; no real-user completion or preference result is available. No production data was accessed or changed.
