# V4 Chat vs Typed Interaction Evaluation

Status: protocol prepared; no human matched-pair run completed. All human outcome metrics below are **unmeasured**.

## Study design

Use the same participant, equivalent synthetic task sets, and counterbalanced order (A→B for half, B→A for half). Do not expose task data from one condition to the other. Chat-only means no typed interaction controls; typed condition uses the relevant existing control. Keep account state, task count, deadline, and constraints equivalent. Record correctness first; do not assume typed UI is faster or preferred.

## Matched tasks

| Scenario | Goal | Chat-only | Typed interaction | Correct final state |
| --- | --- | --- | --- | --- |
| Priority | Rank A, B, C. | “B first, A second, C third.” | PriorityRanker. | Plan ordering matches the user's exact ranking; permanent priority unchanged. |
| Time move | Move one task from 14:00 to 16:00. | Explicit natural-language edit. | Timeline direct manipulation. | Same local wall time and timezone; unrelated schedule unchanged. |
| Conflict | Requested interval is occupied. | Explain the conflict and choose an alternative in chat. | ConflictResolver. | User's selected candidate is preserved; no silent apply. |
| Overload | Tomorrow cannot fit every unfinished task. | Discuss which item to keep/defer. | Day Closing unplaced-choice UI. | Selected/omitted tasks are explicit; no deadline/status changes. |
| Completion | Report that one task took longer than expected. | “This took longer than expected.” | Completion Harvest. | Completion remains true; optional feedback saved once. |

## Record per attempt

`task completion correctness`, `user turns`, `typed text submissions`, `structured interactions`, `clicks/taps`, `clarifications`, `invalid actions`, `undo`, `recovery`, `final state correctness`, participant preference, and task abandonment. Measure decision time only with a consistent observer start/end rule; otherwise write `unmeasured`.

Do not save real task titles, private schedules, full prompts, email, or chat transcripts. Use synthetic or sanitized task IDs and event codes.

## Interaction selection audit

For each prompt, specify expected behavior before running it:

| Prompt class | Expected interaction | Error categories |
| --- | --- | --- |
| Clear single read or change | Chat/no forced UI | unnecessary, wrong, duplicate |
| User uncertainty | Offer choices if consequential | missing, wrong |
| Several items to order | Consider PriorityRanker | missing, wrong, duplicate |
| High-risk write | Approval | missing, wrong, duplicate |
| Pure query | No interaction | unnecessary, wrong, duplicate |

Count each category from a pre-registered scenario denominator. The current priority Agent regression explicitly asks for a Priority UI and therefore does **not** estimate the Agent's independent interaction choice. Appropriate Interaction Rate is presently **unmeasured**.
