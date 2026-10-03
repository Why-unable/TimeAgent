# TimeAgent V4 Iteration 2 — Daily Loop Productization

Date: 2026-10-03
Branch: `codex/agent-ux-v3-interactive-loop`
Scope: Morning Brief, Today Now / Next / Later, Day Closing → Tomorrow Draft, explicit overload handling, Harvest visual treatment, and the real-Agent Apply rejection gate. Production is out of scope.

## Product behavior

- Today summary buckets and completed / unfinished task facts come from `TodayService`; browser clock changes do not reshuffle items.
- Now shows current calendar blocks and in-progress tasks. Next shows the earliest upcoming start time. Later shows subsequent items, overdue tasks, tasks whose planned block has passed, and unscheduled tasks due today.
- Morning Brief shows an existing run preview or launches the selected date through the Briefing Run API only after the user clicks. A new run enters Briefing Workflow directly.
- Day Closing shows today's completed work as a harvest and starts with no carry-over tasks selected. The user chooses tasks and generates a `plan_tasks_only` draft for tomorrow in their IANA timezone.
- Every draft explicitly reports placed and unplaced task counts. Unplaced task names stay visible. The user can keep the draft for review or explicitly abandon it and return with unplaced tasks unchecked. Source tasks and their due dates remain unchanged.
- Plan application remains a separate review and HITL action. Draft creation does not update task schedule fields or create calendar events.

## Idempotency and time handling

Day Closing sends a stable UUID `operation_id` when retrying the same selection after a failed or ambiguous response. Changing the selection resets the operation ID. `SchedulePlan` has a conditional per-user unique constraint; plan creation uses the existing user schedule-write lock and returns the existing plan for an identical request. Reuse of the key with different planning constraints returns a validation error.

The date range is local midnight tomorrow through local midnight the following day, converted using the Today API's IANA timezone. Stored and transmitted instants remain UTC.

## Overload decision

The user first chooses which unfinished tasks to include. If the selected day cannot fit everything, the new `明日安排取舍` surface offers four concrete next steps:

- Keep the unplaced items in the draft for later review.
- Open the current draft and adjust it manually.
- Abandon the current draft and edit an unplaced task's estimate or buffers in the existing Task Editor, then create a fresh draft.
- Remove unplaced items from the draft and return to task selection.

The app does not silently shorten estimates, sacrifice buffers, defer or complete tasks, delete tasks, or change deadlines. Task estimate and buffer edits happen only after the user opens and saves the existing Task Editor. Deadline-first versus focus-first scheduling remains deferred because Planning does not yet persist and review those competing policies.

## Apply rejection gate

The staging scenario uses a real browser and real Agent model to create a draft, asks the Agent to submit it for HITL approval, then creates a calendar event overlapping a proposed slot before the user approves. It expects the apply revalidation to fail, the plan to become invalidated, task planned timestamps to remain unchanged, and the Approval UI to show failure with a link to inspect the plan. Test cleanup removes the staging event and clears fixture task scheduling. No production data is used.

## Architecture decision

The Planning page continues to route Apply through the existing AgentRun → ActionProposal → HITL path. A direct deterministic UI-origin ActionProposal would reduce latency and model selection risk, but the current proposal schema and resume lifecycle require an AgentRun. A synthetic run is not created; a service-level change to support a genuine UI-origin proposal remains a separate design decision. See [ADR 0037](../decisions/0037-daily-loop-tomorrow-draft-and-execution-surface.md).

## Evidence and limits

### Automated checks

- Backend full suite: `uv run pytest -q` — **697 passed, 3 skipped, 1 warning**.
- Backend lint/format/system checks: Ruff passed; all 13 changed backend files passed `ruff format --check`; `manage.py check` passed; test-settings migration check reported no changes.
- Mypy: **30 existing findings across 7 existing files**, matching the baseline audit; no new mypy findings were introduced by this iteration.
- Frontend: **34 files / 167 tests passed**, ESLint passed, and the production build passed. Main bundle is **599.45 kB minified / 184.09 kB gzip**; the existing >500 kB warning remains. The Task Editor used by overload recovery is lazy-loaded.
- OpenAPI JSON and generated frontend TypeScript were regenerated for the Today and schedule-plan contracts. Generation succeeded with one enum naming warning.
- A repository-wide `ruff format --check .` reports 41 existing formatting differences in unrelated files. Changed files pass the scoped check.

### Isolated staging results

Compose project `time-agent-v3-staging` received the current branch images; migration `planning.0007_scheduleplan_operation_id_and_more` applied to its isolated database. GHCR returned TLS timeouts during backend image builds, so the staging-only build used the locally cached `uv:0.11.1` image; dependency installation remained locked with `uv sync --frozen`, and no repository Docker configuration changed. The dedicated real-Agent browser suite passed **2/2** on `127.0.0.1:7081`:

1. Priority interaction persisted a plan-only reorder across runs.
2. A real Agent draft entered HITL approval; after a conflicting calendar event was created, Apply revalidation rejected it, the plan became invalidated, task planned timestamps and Today schedule facts stayed unchanged, and Approval UI showed the failure and plan-review link.

The first execution found a bug: the Agent returned a recoverable `ToolMessage(status="error")`, but the audit layer marked the tool and proposal executed. The middleware now records returned error messages as failed in `ToolCallAudit` and `ActionProposal`, while preserving the error result for the Agent. The focused regression test and the staging journey pass with that fix. Production was not touched.

Automated coverage verifies code behavior, accessibility semantics, API state, and the local real-Agent staging flow. It does not establish a matched human UX improvement, physical screen-reader result, or production deployment.
