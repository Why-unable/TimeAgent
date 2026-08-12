# ADR 0021: Immutable run anchors and deterministic relative event time

- Status: Accepted
- Date: 2026-08-12

## Context

A conversation checkpoint contains messages from multiple wall-clock moments. Model attention can
incorrectly reuse a stale clock statement or relative expression from an older turn even when the
current system prompt provides a fresh runtime anchor. Prompt instructions alone cannot make date
arithmetic deterministic, and queue delays or HITL resumes must not redefine what the user meant by
"now" when the request was accepted.

## Decision

Each `AgentRun` persists an immutable UTC `anchor_at` and the IANA `anchor_timezone` captured by the
Application Service when it accepts the request. Initial execution and every checkpoint resume use
that same anchor. A later user message creates another run and therefore another anchor.

Event write tools accept one discriminated `time` union. `kind="absolute"` contains only an aware
start/end pair. `kind="relative"` contains the source phrase, bounded offset/unit, optional local
wall-clock time, and duration. The model chooses the variant from the latest request; it must not
calculate an absolute pair for relative wording. The backend does not inspect prose with regular
expressions and does not call another model to classify intent. Pydantic rejects missing, mixed, or
unknown variants, and `EventTemporalResolutionService` is the single validation/resolution path
used by tool execution, conflict previews, and approval display. It resolves relative input against
the trusted run anchor and timezone, including DST validation. The event tool records a sanitized
`temporal.resolved` audit event before calling the existing event Application Service.

The authoritative checkpoint retains original messages. `TemporalContextMiddleware` supplies the
model with a derived history view: old clock tool results are removed and both historical roles are
labeled with their original run anchor. Historical content itself is not regex-filtered. The latest
user message remains unchanged. No extra current-turn message is inserted next to it.

The real-model trajectory evaluation supports multiple turns with distinct anchors and verifies
that relative event writes use `time.kind="relative"` instead of absolute times.

## Consequences

- Relative event time is deterministic even when the model's semantic attention is influenced by
  old conversation content.
- Celery delay and HITL approval delay do not shift the meaning of the accepted request.
- Ambiguous or nonexistent local wall-clock times fail closed and require clarification.
- Original conversation and business data remain auditable; the model receives only a safer view.
- Existing explicit absolute date-time event requests remain supported.
- Correct variant choice is an evaluated model contract rather than a brittle keyword detector;
  structural correctness and all date arithmetic remain deterministic backend responsibilities.
