# ADR 0029: Automation Policy and Reversible Schedule Changes

- Status: Accepted
- Date: 2026-08-24

## Context

Phase E must not turn a local replan preview into an implicit calendar mutation. A user needs an explicit scope, a bounded move count, and a way to restore the prior schedule.

## Decision

Persist `AutomationPolicy` as the authorization boundary. Enabling a policy requires `allow_task_reschedule=true`; each run is capped by `max_moves_per_run`. Mutations are recorded in `ScheduleChangeBatch` with operation id, policy reference, before/after snapshots, status, and timestamps. Revert revalidates the post-apply task version before restoring the snapshot through `TaskService`.

The direct apply API accepts a caller-generated operation id and recomputes the preview from authoritative facts. It may execute only when the selected policy is enabled, allows task rescheduling, and has `requires_approval=false`. Policies that require approval fail closed on the direct API. Time Steward exposes a separate high-risk `apply_local_replan` Tool; the existing HumanInTheLoop middleware persists its interrupt as an ActionProposal and resumes the same Agent thread only after approval. Apply holds the user schedule write lock and revalidates task versions, current event/task conflicts, and overlap among proposed moves.

`AdaptivePlanningService.detect_disruptions` deterministically compares active planned Task intervals with non-cancelled CalendarEvent intervals and returns the impacted task/event, exact overlap, and reason code without mutation. The shared planning page renders this as an impact timeline and can prefill the bounded preview. Policies can be patched to pause/resume, change their move cap, or persist an owned Task UUID allowlist without deleting audit history.

The deterministic Celery dispatcher considers only enabled, no-approval policies with a non-empty allowlist. It detects current overlaps, moves at most the policy cap, derives an operation id from policy/task version/event/overlap, and reuses the same transactional apply boundary. Policies without a persistent allowlist remain manual even when legacy API calls provide movable IDs. Time Memory derives aggregate accepted/reverted/user-modified counts from existing `ScheduleChange` facts; this evidence never expands the allowlist or changes approval policy.

## Consequences

- Preview and mutation are separate operations.
- Replayed operation ids return the original change batch instead of moving tasks twice.
- Stale tasks or changed-after-apply tasks fail instead of being silently overwritten.
- External calendar write-back, Provider compensation and a real-data stability benchmark remain future capabilities.
