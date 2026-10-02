# ADR 0036: Versioned Plan Interactions and Apply Approval

- Status: Accepted
- Date: 2026-10-03

## Context

Priority ranking and timeline editing are separate persisted interactions over the same mutable plan draft. Advancing a draft version must not make an older pending interaction appear current. In addition, applying a plan changes authoritative Task and Event facts and must use the repository's ActionProposal and HITL approval boundary, regardless of whether the request starts in Chat or Planning.

## Decision

When an accepted plan edit advances SchedulePlan.version, every other pending interaction for that plan becomes stale and receives a resolution timestamp. The interaction that performed the accepted edit remains pending at the new plan version. A stale submission returns HTTP 409. Ensuring a plan interaction for the current version creates a fresh artifact rather than reviving a stale one. The backend remains the authority for plan versions and accepted edits.

The Planning page does not call the plan-apply endpoint directly. Its “提交应用审批” action opens Chat with the exact plan ID and version in the request so the Agent creates the existing apply_schedule_plan ActionProposal. The formal approval card remains the single execution confirmation. Failed or ambiguous apply results direct the user to refresh and inspect the schedule before retrying.

## Consequences

- Interaction status adds a persisted stale state and the API schema exposes it.
- Stale interactions cannot mutate a newer draft; clients refresh the plan and reopen a current interaction.
- Applying a plan initiated from Planning now goes through the same AgentRun, ActionProposal, and HITL resume path as applying from Chat.
- A manual Apply failure must not claim that the schedule was unchanged unless the refreshed authoritative state proves that fact.

## Alternatives considered

- Update sibling interactions to the latest plan version: rejected because an old UI would silently gain write authority over new draft content.
- Keep the direct Planning Apply endpoint for convenience: rejected because it bypasses the mandatory high-risk ActionProposal/HITL lifecycle.
- Compute a replacement time in the browser: rejected because availability and conflict decisions remain backend-owned.
