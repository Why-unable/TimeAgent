# UI-Origin ActionProposal Options

Status: design analysis only; no ActionProposal lifecycle or write-path changes in V4 validation. Current Planning Apply still uses the AgentRun → ActionProposal → HITL path described by [ADR 0036](0036-versioned-plan-interactions-and-apply-approval.md).

## Options

| Concern | A — Current AgentRun-origin | B — Genuine UI-origin proposal | C — Unified `ProposalOrigin = agent | ui | automation` |
| --- | --- | --- | --- |
| Authorization | User starts in Planning, then AgentRun owns the proposal; existing authorization checks and caller identity remain central. | UI request must still prove authenticated owner, plan/version, and permission to propose; UI cannot directly execute. | One service can apply common owner/risk policy while validating origin-specific actor permissions. |
| Audit | AgentRun, conversation, selected tool, and proposal are linked; extra Agent latency/tool selection is visible. | Store authenticated user + UI surface/action + plan/version; no synthetic conversation/run. | Store explicit origin and actor; retain optional AgentRun/conversation references only for Agent origin. |
| HITL | Existing approval card and proposal decision state already work. | Must create a proposal that enters the same approval card/state machine before execution. | Common approval state machine can serve all origins if origin metadata does not bypass risk policy. |
| Resume | Approval decision resumes the owning AgentRun; UI-origin has no truthful run to resume. | Approval execution completes deterministically without Agent resume; define an explicit completion result for Planning. | Resume policy is origin-specific: Agent resumes its run; UI/automation dispatch their own explicit continuation. |
| Idempotency | AgentRun/tool idempotency and proposal identity apply. | UI request needs a stable operation ID scoped by user, plan, version, and action; duplicate submission must return the same proposal. | Unified key policy with origin included; reject same key with a different request fingerprint. |
| Execution ownership | AgentRun owns orchestration; approval gates action execution. | Application service owns execution after approval; browser never owns the mutation. | Proposal service owns the common transition; origin adapter owns continuation after approval. |
| Conversation history | Naturally appears in Chat history and tool activity. | Must remain discoverable from Planning and the Approval surface without inventing chat transcript entries. | Store origin-linked activity; only Agent-origin records need a conversation entry. |

## Recommendation

Do not create a synthetic AgentRun or bypass `ActionProposal`/HITL. Keep option A until the current path is shown to be a release blocker. If latency/tool selection proves costly in measured use, prototype B with a genuine UI actor and same approval state machine. Prefer C only after at least two non-Agent origins actually need the shared lifecycle; otherwise it risks an unused abstraction. Any future lifecycle change requires service-level idempotency/audit design, an ADR amendment/new ADR, migration/API schema regeneration if contracts change, and end-to-end approval/resume tests.
