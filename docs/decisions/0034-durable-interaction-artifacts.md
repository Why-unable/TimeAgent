# ADR 0034: Durable typed Interaction Artifacts

- Status: Accepted
- Date: 2026-10-02

## Context

Interactive Planning and Completion Check-In need to survive reloads and concurrent edits. Conversation events already preserve references to schedule plans, while `ActionProposal` represents higher-risk approval and resume. Neither is the right source of truth for low-risk direct manipulation or optional completion feedback. A plan draft must remain separate from applied Task facts, and plan-local ranking must never be written into permanent `Task.priority`.

## Decision

Add PostgreSQL-backed `InteractionArtifact`, `InteractionSubmission`, and allowlisted anonymous `InteractionTelemetryEvent` records in the `interactions` app. Artifacts are owned by a user, may link to a conversation/run, and point to either a schedule plan or a completed task. The typed payload contains structured data and references only. Submissions persist `expected_version`, allowlisted action/value data, result, and a per-user idempotency key.

All artifact reads and submissions go through `InteractionArtifactService`. The Time Steward may request one allowlisted planning interaction type through a typed tool; it returns only artifact references and structured data. Plan changes delegate to `PlanningService.edit_schedule_plan`, which validates under the existing schedule write lock. The plan remains a draft; accepted schedule estimates and timing are committed through the existing TaskService path only at Apply, and high-risk Agent-initiated Apply retains its HITL boundary. Completion self-report is stored separately from measured execution signals. Completion creates the optional check-in in a nested savepoint so its failure does not block the task transition; replay attempts recovery. A lasting duration-profile change can only happen through the existing explicit Time Memory feedback service after a dedicated user action and sufficient evidence.

Telemetry accepts only enumerated event names, interaction types, counts and bounded duration/ratio values. The persisted telemetry row has no user, task, conversation, title, free-text reason, or message field.

## Consequences

- A database migration and authenticated API are required to restore pending interactions and persist decisions.
- Plan order is scoped to `SchedulePlan.items`; it does not modify Task priority or directly reschedule tasks.
- Schedule edits use the existing deterministic validator. Failed edits return backend reason codes, conflicting schedule facts and a candidate only when that candidate passes the same deterministic validation.
- Expiry, status, optimistic versions, and idempotency history become explicit parts of the interaction lifecycle.
- User feedback labels are self-reported and must not be represented as timer-derived duration evidence.
- Physical device, assistive technology, user acceptability, and fresh holdout results remain empirical requirements; the data model itself does not prove UX quality.

## Alternatives considered

- Reuse generic `AgentEvent`: rejected because it does not provide independent lifecycle state, expiry, optimistic concurrency, or idempotent decision history.
- Reuse `ActionProposal`: rejected because its approval/resume semantics are intended for higher-risk business mutations.
- Store interaction UI in Agent messages: rejected because UI markup is frontend-owned and must remain stable and accessible.
