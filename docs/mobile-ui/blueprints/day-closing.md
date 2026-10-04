# Day Closing Blueprint — Iteration 3 polish

Status: existing Day Closing and Tomorrow Draft remain functionally implemented and are out of the Iteration 1 flow redesign; Iteration 1 applies only a contrast correction to the existing harvest surface.

Keep the Today surface compact: show a short harvest count and “整理明天” action. The existing harvest area uses a solid white surface with dark title/body text and a clear amber border for stable contrast. The current inline task-selection and tomorrow-draft behavior is unchanged in Iteration 1. A later pass may open the existing explicit task-selection and tomorrow-draft flow in a focused full-height sheet. Default to no carry-over tasks selected. Preserve operation ID retry behavior, local-midnight/IANA timezone boundaries, unplaced task visibility and the separate review/HITL apply path from ADR 0037.

Specify no completed tasks, unfinished tasks, overloaded day, pending draft, stale/error/offline, retry, focus restoration and keyboard states before changing the flow.
