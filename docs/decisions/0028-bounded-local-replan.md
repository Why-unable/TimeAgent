# ADR 0028: Bounded Local Replan Preview

- Status: Accepted
- Date: 2026-08-24

## Context

Phase E needs a safe first step for schedules disrupted by a blocked interval. A full autonomous rewrite would violate the current product boundary and make trust, rollback, and external-calendar consistency harder to prove.

## Decision

`AdaptivePlanningService.preview_local_replan` accepts an explicit list of movable task IDs and returns a review-only diff. It reuses the deterministic free-slot service, emits before/after timestamps, reason codes, moved count, total/max movement minutes and unplaced count, and never mutates tasks or events. Applying a preview is a separate service operation subject to Automation Policy, version checks, current-fact revalidation and authorization.

## Consequences

- The initial adaptive behavior is bounded, explainable, and testable.
- Locked or unspecified objects are not moved implicitly.
- Automation Policy, ActionProposal/HITL approval, undo and change-batch audit are implemented; external write-back and Provider compensation remain future work.
- A deterministic synthetic benchmark compares bounded repair with full compaction, but its result is not a product outcome.
