# TimeAgent V4 — Product Interaction Language / Daily Loop

Date: 2026-10-03
Branch: `codex/agent-ux-v3-interactive-loop`
Scope: V4 UX audit, P0 interaction hardening, and Iteration 2 Daily Loop Productization; no Agent Harness or Tool Discovery redesign.

## Current UX Audit

This first-pass audit traces the current UI and backend interaction paths before V4 changes. The click and text counts below are **minimum path estimates from the rendered controls**, not observed user analytics. The repository has interaction telemetry events, but no trustworthy journey-level denominator for user turns, clicks, or completion time; those metrics remain **unmeasured** until a matched browser study is run.

### Current Journey Map

| # | User goal / current page | Minimum clicks or actions | Text input | Page hop | Repeat confirmation / terminology | State clarity, undo, Plan vs. Schedule |
|---:|---|---:|---|---|---|---|
| 1 | Open TimeAgent in the morning / Today | 0 after landing; 1 nav if arriving elsewhere | None | Possible | “今日节奏” exists on mobile; no morning summary of focus load or top priority | Empty state offers a next step. The daily brief is incomplete. |
| 2 | Ask for today's plan / Today → Chat | 1 “帮我安排今天” action; prompt auto-sends | None; preset request | Yes, Today → Chat | Chat and tool activity can both explain work; technical trace is expandable | Plan preview is explicitly a draft; no single daily-loop surface. |
| 3 | Review the generated plan / Chat | 0 to view; may need scroll | None | No | Plan card and Agent prose can repeat the same explanation | Draft badge exists. Unplaced items and trade-offs are not consistently summarized first. |
| 4 | Change task order / Chat plan card | 1 open interaction + 1 action per move (or drag) | None | No | Uses “本次计划” language; permanent task priority is protected | Autosaves the draft and says so. Undo is not available for ordering. |
| 5 | Move a task in time / Chat plan card | 1 open interaction + 1 drag or keyboard save | None | No | Timeline describes drag mechanics before the user acts | Draft boundary is stated; latest edit is locally undoable. There is no compact multi-item diff. |
| 6 | Apply the plan / Chat or Planning | 1 Apply action; approval action when HITL interrupts | None | Sometimes | Chat Apply/HITL can feel like separate confirmations; Planning also has a direct Apply control | Applied badge exists, but Apply validation failure lacks a focused recovery explanation. |
| 7 | Start executing a task / Today | 1 tap on the mobile “开始” action; desktop task list has no equivalent start action | None | Possible to Tasks/Chat for desktop workaround | “进行中” is shown on the mobile next action | Desktop/mobile execution affordances differ; status should be more consistent. |
| 8 | Tell TimeAgent a task is taking longer / Today → Chat | 1 navigation + 1 send action | One short update | Yes | No dedicated overrun decision surface | User must explain the change in text; impact on the existing plan may not be shown as a diff. |
| 9 | Add an unexpected meeting / Calendar or external calendar | At least 1 navigation; event creation adds form actions | Event details unless synced | Yes | Calendar operation may be separate from replanning | Existing conflict facts are surfaced on Today; no automatic “what changed” summary is guaranteed. |
| 10 | Replan around the meeting / Chat or Planning → local adjustment | Chat: 1 request; manual mode: several fields, selection, detect, preview, then apply | Chat request or manual time fields | Often | “局部调整”, “策略”, and “检测扰动” expose implementation concepts | Deterministic preview and undoable batch exist in manual flow; Agent and manual plan review are split. |
| 11 | Mark a task complete / Today | 1 completion action | None | No | No second confirmation | Completion is saved before feedback is requested. This is the correct safety boundary. |
| 12 | Give optional completion feedback / Today | 1 rating + 1 save, or 1 skip | Optional reason is currently shown at the same time | No | Several reason choices increase the default decision surface | Skip is available. Feedback does not gate completion. |
| 13 | Accept an estimate suggestion / Today | 1 accept or keep-current action | None | No | “Time Memory” appears in explanatory copy | Suggestion is consent-based and tied to an interaction artifact. |
| 14 | Review unfinished work at night / Today | 0 to review lists | None | No | No Day Closing flow exists | User can see unfinished tasks, but there is no concise day summary or clear next-day handoff. |
| 15 | Create tomorrow's draft / Chat or Planning | 1 Chat prompt + send, or several Planning form actions | Natural-language prompt in Chat | Often | Must find the separate planning entry point | Tomorrow Draft exists as a concept, but it is not produced from Day Closing; applied Task/Event boundary remains backend controlled. |

### Audit findings and priority

1. **Stale interaction race (P0 correctness):** after a priority interaction edits a plan, the backend advances the stored `plan_version` on every other pending interaction for that plan. A stale timeline card can therefore appear current and write against the updated draft. The API checks versions, but the sibling artifact is silently refreshed instead of invalidated.
2. **Apply failure recovery (P0 correctness):** Planning displays the raw mutation error through a generic `ErrorText`; the page does not explicitly state that the saved Task/Event schedule was not changed or offer a direct retry/review action.
3. **Conflict recovery (P0 interaction):** timeline editing receives deterministic `reason_codes`, `conflicts`, and a backend `candidate`, but the UI renders these within a generic error block. A named Conflict Resolver can make “why unavailable” and the backend-provided next option clear without inventing times in the browser.
4. **Plan review and change comprehension (P0):** users see a full draft again after edits/replanning and must infer which items changed. Existing per-item confirmation text is not a reviewable multi-item diff.
5. **Completion decision cost (P0 polish):** completion itself is correctly immediate and feedback optional. The default card presents rating and reason together; reason can be progressively disclosed and the completion state can be expressed more consistently without blocking.
6. **Daily continuity (P1):** Today is a useful schedule/task overview but lacks a concise Morning Brief, stable Now/Next/Later execution grouping on all screen sizes, and Day Closing → Tomorrow Draft.
7. **Product language (cross-cutting):** most core copy is understandable, but Planning's manual replan surface exposes “策略”, “局部调整”, and operational vocabulary; Chat's “执行详情” reveals raw tool names only after expansion. Default wording can be more user-centered while preserving an advanced trace.
8. **Responsive evidence:** existing tests cover desktop and mobile layouts, but the V4 journeys need a real browser pass at 375px and 430px, including keyboard entry, conflict recovery, and feedback focus. No V4 real-staging result is claimed yet.

### Current state language audit

| State | Current expression | Audit |
|---|---|---|
| Draft | “计划草案” / “草案” | Present, but varies across Chat and Planning. |
| Applied | “已应用” / “计划已应用” | Present; strengthen by tying it to formal schedule changes only after server success. |
| Pending approval | Approval card status “等待审批” | Visually separate from normal editing; preserve this distinction. |
| Completed | Task status / optional harvest card | Completion is committed first; the harvest remains optional. |
| Conflict | Generic reason text and error container | Needs concrete conflict title, occupied interval, candidate, and recovery action. |
| Suggestion | Memory estimate suggestion | Consent buttons are clear; user-facing copy can omit internal subsystem labels. |
| Undo | Timeline single-edit undo; local replan batch revert | No consistent undo language for all plan edits; must not imply applied schedule can be undone unless server confirms. |

## Iteration log

### Baseline — 2026-10-03

- Completed source-level audit of Today, Chat plan artifact, Planning, Approval, Timeline, Completion Harvest, InteractionArtifact API/service, and schedule plan apply paths.
- Identified P0 implementation order: stale interaction invalidation, deterministic conflict resolution presentation, apply-failure recovery, compact plan diff review, and progressive completion feedback.
- Baseline counts above are source-derived minimum path estimates. There is no matched user-study or reliable journey-level denominator, so they are not presented as measured outcomes.

### Iteration 2 — Daily Loop Productization — 2026-10-03

- Added a server-owned Now / Next / Later execution surface, with completed and unfinished task summaries from `TodayService`; the browser does not reclassify schedule items.
- Added a user-triggered Morning Brief entry that starts the existing Briefing Workflow directly, plus Day Closing with a Tomorrow plan draft, local-time boundaries, and an idempotent operation ID.
- Added an explicit overload decision when tasks do not fit the selected day: keep the unplaced work in the draft, adjust the draft manually, revise a task's estimate or buffers before replanning, or remove unplaced items and select again. Revising task inputs first abandons the old draft; no task is silently shortened, deferred, completed, or deleted.
- Added a real-Agent staging Apply-rejection journey. The first run exposed a status bug: a recoverable `ToolMessage(status="error")` was being recorded as completed/executed. Tool audit and ActionProposal now record it as failed while returning the error to the Agent; the user-facing recovery message and unchanged Task/Today facts are asserted in staging.
- The product behavior and release evidence are recorded in [Iteration 2 — Daily Loop Productization](agent-ux-v4-iteration-2-daily-loop.md) and [ADR 0037](../decisions/0037-daily-loop-tomorrow-draft-and-execution-surface.md).

## Product Interaction Language

The implemented hierarchy keeps the user's decision in front and exposes internal details only when they help recovery:

- Plan review shows whether a plan is a draft or already applied, then summarizes changed items and locked/unplaced reasons in one review surface.
- Conflict recovery explains the backend's reason, occupied interval, and backend-provided candidate. The browser does not invent a time or candidate.
- An apply failure points back to the specific plan so the user can reload its current state. It does not claim that the formal schedule changed.
- A stale approval is re-presented against the current plan and requires a second approval. It is not silently executed against a changed preview.
- Completion is saved independently; optional feedback stays optional, progressively discloses reasons, and returns focus to the saved status.
- Approval copy distinguishes an edit awaiting review, a stale proposal awaiting renewed approval, processing, execution, and failure.

## Journey Before / After

The source-level journey estimates above remain the baseline. The same scripted journeys now exercise the changed paths in frontend/component and browser tests, but those automated interactions are not a matched human study and do not establish lower user effort or improved task-completion rates. Browser traces verify the implemented states and recovery actions; observed user counts, completion time, and preference remain **unmeasured**.

## Existing and planned components

Existing: `PlanPreview`, `InteractivePlanTimeline`, `PriorityRanker`, `ApprovalCard`, `CompletionHarvest`, `MemorySuggestionCard`, and the Interaction Component Registry.

Implemented P0: `PlanDiffReview` and `ConflictResolver` as focused components; stale state remains at the existing artifact boundary rather than introducing another persistence layer.

Implemented in Iteration 2: `MorningBrief`, `ExecutionSurface`, and Day Closing with an explicit overload decision. The Day Closing flow reuses the Task Editor for user-selected estimate or buffer changes and the existing Planning draft/apply boundary.

Rejected for this iteration: a full fruit-game animation system, a second Agent/Planner abstraction, and client-computed availability candidates. These do not address the highest correctness gaps and would add new cognitive or architectural cost.

## Implementation and review record

### P0 changes

- Interaction artifacts now have an explicit stale lifecycle. Editing a plan invalidates sibling pending artifacts, and submitting one returns a conflict rather than applying an obsolete edit.
- Plan application no longer has a direct schedule-plan endpoint. Apply goes through an `ActionProposal` and HITL approval. A plan-version change between proposal and approval refreshes the proposal and requires the user to approve the refreshed version.
- Planning now presents a compact plan diff, backend conflict details, a recoverable `plan_id` link after apply failure, and an explicit keyboard-operable tablist. Opening the recovery link reloads the selected plan from the API.
- Completion feedback progressively discloses reasons, retains completion as an independent committed action, respects reduced motion, and restores focus to the saved state.
- Approval outcome language and announcements now distinguish edits, stale re-review, processing, execution, and failure, including repeated identical decisions.
- OpenAPI and generated frontend types were regenerated after removal of the direct apply endpoint. The lifecycle decision is recorded in [ADR 0036](../decisions/0036-versioned-plan-interactions-and-apply-approval.md).

### Critic loop

- Accessibility review identified missing focus restoration after completion save and interaction-load failure, small touch targets, and incomplete tab keyboard behavior. These were addressed with focused status targets, 44px Today controls, and roving arrow/Home/End tab navigation; tests cover the behaviors.
- Adversarial review identified a direct-apply route that bypassed HITL, stale local plan state after failure, generic conflict explanations, and approval against a newer plan preview without renewed approval. The direct route was removed, recovery now reloads the referenced plan, reason codes are mapped to plain language, and a stale proposal must be reviewed and approved again.
- Final adversarial review of the supplied implementation snippets found no remaining P0/P1 approval or recovery gap. This was a snippet review, not an independent execution of the repository. The latest accessibility critic could not inspect the latest tree; real screen-reader hardware testing also remains outstanding.

## P1 decision

The overload decision, Day Closing → Tomorrow Draft, and consistent Today execution surface were deferred from the original P0 pass and have now been implemented in Iteration 2. Explicit task estimates and buffers can be changed through the existing Task Editor after the current draft is abandoned; the user then generates a fresh draft. Alternative global strategies such as deadline-first versus focus-first remain deferred because Planning does not yet persist those trade-offs for review. A matched user study remains necessary before claiming that the new journey reduces effort.

## Accessibility, mobile, real-browser results, and remaining work

- Backend: `uv run pytest -q` — **695 passed, 3 skipped**. The skips are the documented LangGraph async interrupt limitation and opt-in live-notification tests.
- Backend static and Django checks: Ruff passed; Django system check reported no issues; `makemigrations --check --dry-run` reported no changes.
- Frontend: Vitest — **32 files / 161 tests passed**; ESLint passed; production build passed. The main bundle is **599.28 kB minified / 184.02 kB gzip** and Vite still reports its >500 kB chunk warning. This is a small increase from the previously recorded approximate ~596 kB baseline; the comparison is directional, not a fully normalized build benchmark.
- Mocked browser E2E: Chromium desktop — **38 passed, 2 skipped** across interactive planning, smoke, and desktop workspace. Mobile Chromium interactive planning — **11 passed, 2 skipped**, including keyboard paths, 320/375/430px layouts, touch drag, stale conflict refresh, completion recovery, and reduced-motion behavior. Pointer-only cases skipped under the mobile project are expected project-level skips.
- Type checking: `uv run mypy .` still exits non-zero with **30 findings across 7 files**. They include existing nullable-relation and typing issues in `interactions/models.py`, `interactions/views.py`, `planning/services.py`, `agents/middleware.py`, tool-discovery code/tests, and one `BaseTool.func` access in `tests/test_interactions.py`; no mypy-clean result is claimed.
- Automated tests verify keyboard semantics and focus targets, but this iteration did not run a physical-device or screen-reader session.
- Matched Chat-vs-typed human UX evaluation was not run. Improvement in clicks, completion time, or user preference is therefore **unmeasured**; this iteration claims implementation and technical verification only.
- Isolated staging: the current branch images were rebuilt under Compose project `time-agent-v3-staging`; migration `interactions.0004_alter_interactionartifact_status` applied successfully and `/health/live` returned HTTP 200. The real-browser staging scenario **passed (1/1)** with the dedicated test account and real Agent model: browser-created tasks → real Agent plan → interaction opened across reload → user-only priority reorder persisted without changing permanent task priorities → timeline interaction → past-time edit rejected with the specific reason → natural-language past-time request rejected without changing the plan. This scenario intentionally did not apply the plan.
- Production has not been modified. No production deployment or release tag is part of this iteration.

The remaining validation limitation is the missing matched human UX study and physical screen-reader session. These are recorded as unmeasured rather than inferred from automation.

### Iteration 2 verification — 2026-10-03

- Backend: full `uv run pytest -q` — **697 passed, 3 skipped, 1 warning**. Ruff lint passed. All 13 changed backend files passed `ruff format --check`; `manage.py check` and `makemigrations --check --dry-run --settings=config.settings.test` passed.
- Type checking: `uv run mypy .` remains at **30 findings across the same 7 existing files** recorded by the baseline audit. No new mypy findings were introduced in this iteration; the changed Today serializer was kept on its existing typed enum-value pattern.
- Frontend: **34 files / 167 tests passed**, ESLint passed, and the production build passed. Main chunk: **599.45 kB minified / 184.09 kB gzip**; Vite's existing >500 kB warning remains. The Task Editor used by overload recovery is lazy-loaded.
- Contract: OpenAPI JSON and generated TypeScript were regenerated for the Today and schedule-plan API changes. Generation succeeded with one enum naming warning; no schema mismatch was reported.
- Staging: Compose project `time-agent-v3-staging` received the current Django, Celery, and frontend images. Migration `planning.0007_scheduleplan_operation_id_and_more` applied to the isolated staging database. GHCR returned TLS timeouts during backend image builds, so the staging-only build used the locally cached `uv:0.11.1` image; dependency installation remained locked with `uv sync --frozen`, and no repository Docker configuration changed. The restricted real-Agent browser suite passed **2/2**: priority interaction persisted as plan-only state, and a late calendar conflict caused Apply rejection, an invalidated draft, unchanged Task/Today schedule facts, and clear Approval UI recovery. Production was not modified.
- `uv run ruff format --check .` reports 41 pre-existing formatting differences in unrelated repository files; none were reformatted as part of this work. Changed backend files pass the scoped format check.
- Automated results establish technical behavior only. Matched human UX evaluation, physical screen-reader testing, and production deployment remain unmeasured/out of scope.
