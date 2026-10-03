# ADR 0037: Daily Loop Tomorrow Draft and Today Execution Surface

- Status: Accepted
- Date: 2026-10-03

## Context

The V4 interaction foundation has reliable draft editing and HITL application, but Today still lacks a clear execution surface and a safe handoff from unfinished work to tomorrow. A retry after a network timeout must not create multiple indistinguishable tomorrow drafts. The browser must not become a second authority for time grouping or scheduling outcomes.

## Decision

- `TodayService` owns the Now / Next / Later grouping and the completed / unfinished task summary. It uses the injected request time and the user's IANA timezone. The frontend renders these response fields without reclassifying them.
- Day Closing lets the user explicitly choose unfinished tasks and asks the existing Planning service for a `plan_tasks_only` draft spanning tomorrow in the user's timezone. It does not complete tasks, update their planned timestamps, or create event blocks.
- Schedule plan creation accepts an optional UUID `operation_id`. For a given user, the same ID and identical planning constraints returns the existing plan; reusing it for a different request is rejected. A conditional unique constraint enforces the key and the existing per-user schedule-write lock serializes creation.
- Unplaced tasks remain visible in the draft. The user may keep the whole draft or explicitly abandon it and remove unplaced entries from that draft before selecting again. Abandoning a draft does not remove or reschedule the underlying tasks.
- Morning Brief is launched only by an explicit user action and enters the existing Briefing Workflow directly.
- Plan application continues through the existing AgentRun → ActionProposal → HITL path. A deterministic UI-origin ActionProposal remains deferred until the ActionProposal service no longer requires synthetic AgentRun ownership; do not create a dummy run to avoid a model call.

## Consequences

- The Today API contract includes execution buckets, today's completed tasks, and a deduplicated unfinished task list.
- Schedule plan schema and database migration include optional operation idempotency metadata.
- A lost response can be retried safely by reusing the same operation ID. A new task selection creates a new operation ID.
- The overload choice is explicit and reversible at the draft boundary: the old draft is abandoned, and source tasks remain authoritative and unchanged.
- The Morning Brief surface reuses Briefing Run records and does not duplicate workflow logic.
- The isolated staging gate must include a real Agent plan, HITL approval, a late calendar conflict, rejected application, and task/Today API checks. This is not evidence of a matched human UX study or physical screen-reader use.

## Alternatives considered

- Auto-select and carry every unfinished task into tomorrow: rejected because it can silently overload the next day.
- Drop unplaced tasks from the plan response: rejected because it hides work and the reason it could not be scheduled.
- Recompute Now / Next / Later in the browser: rejected because the backend must remain authoritative for time and status.
- Use a fresh UUID on every retry: rejected because an ambiguous network failure could create duplicate drafts.
- Create a synthetic conversation and AgentRun for Planning-page Apply: rejected because it disguises a deterministic UI action as an Agent action and adds fake lifecycle records.
