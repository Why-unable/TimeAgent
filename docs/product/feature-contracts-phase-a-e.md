# Phase A-E Feature Contracts

This document records the executable boundaries for the current vertical slices. It deliberately marks incomplete capabilities instead of implying a larger system.

## Execution Evidence and Calendar Sync

- **Scenario:** a user records start/pause/complete/skip actions and optionally imports read-only calendar busy time.
- **Rule boundary:** clients and Tools call Application Services; PostgreSQL facts remain authoritative; all timestamps are UTC with an explicit IANA timezone at input/display boundaries.
- **Failure:** duplicate idempotency keys, stale provider cursors, malformed ICS, private/loopback feed targets, disabled connections, and provider errors are surfaced without fabricating events or persisting a secret-bearing Provider exception.
- **Acceptance:** repeated signal/sync requests are idempotent; provider records source/external ID; provider-issued incremental cursors are persisted; deletion tombstones cancel known local events without fabricating unknown events; cancellation is represented as a local event state.

## Google Calendar OAuth Read-Only Connection

- **Problem:** an authenticated user needs real Google Calendar busy-time facts without pasting a private feed URL or granting Time Agent external write access.
- **Input/trigger:** the user explicitly starts OAuth; Google returns a one-time authorization code and opaque state; later the user explicitly or deterministically triggers a bounded read-only sync range.
- **Output/state changes:** an encrypted account credential, one or more user-owned calendar connections, account/calendar-scoped event mirrors, a Provider-issued sync token, and sanitized status are persisted in PostgreSQL.
- **Non-goals:** Google event create/update/delete, webhook/watch channels, Microsoft OAuth, automatic calendar selection, and claiming production readiness without a sandbox run. Bounded Celery polling is implemented; push/webhook delivery is not.
- **AI/rule/human boundary:** no LLM participates. The user grants/revokes access; OAuth, state validation, token refresh, pagination, time conversion, deletion handling, idempotent upsert and errors are deterministic services.
- **Risk/confirmation:** read-only connection is L0/L1 and requires the user's explicit OAuth action. External writes remain unsupported. Public event APIs cannot assign or mutate Provider identity fields.
- **Security:** OAuth state is random, hashed at rest, single-use and expiring; tokens are encrypted with a dedicated server-only Fernet key; API responses/logs/errors never contain tokens, authorization codes, state hashes or private feed URLs; guest accounts cannot connect providers.
- **Failure:** missing configuration, denied consent, state replay/expiry, malformed token response, missing refresh token, refresh failure, 401/403, 429, 5xx, page overflow, sync-token 410, unknown tombstones and transaction failure fail closed with bounded, sanitized outcomes.
- **Acceptance:** authorization URL contains the exact read-only scope and offline access; callback consumes state once; encrypted storage does not contain plaintext tokens; refresh preserves a prior refresh token when Google omits a new one; CalendarList/Events pagination is bounded; 410 performs one full resync and stores the replacement token; all-day/timed/cancelled events normalize correctly; two calendars with the same Provider event ID remain distinct; credentials can be revoked locally; contract tests use fake HTTP transport and a live sandbox remains `NOT VERIFIED` until actually run. `verify_google_calendar` must emit a versioned JSON report, return non-zero on Provider failure, and exclude account/calendar identifiers, URLs, cursors, authorization codes and tokens.

## Deterministic Planning and Free-Time Suggestions

- **Scenario:** a user previews a task plan or asks for future candidate slots before confirming any mutation.
- **Rule boundary:** planner owns work windows, conflicts, deadlines, and reason codes; no LLM performs time arithmetic.
- **Failure:** impossible tasks remain `unplaced`; apply revalidates task versions and plan status; local regeneration rejects tasks outside the draft or stale draft versions.
- **Acceptance:** plan API returns a TTL-bound draft with constraint/profile snapshots and evidence; compare produces two named deterministic alternatives without claiming an optimum; edit/lock/validate/abandon are versioned; regeneration preserves unselected draft blocks; stale facts persist machine-readable invalidation; high-confidence duration calibration is recorded while low confidence is ignored; buffers occupy conflict-tested time; split tasks create multiple blocks only under the linked-event strategy; apply is version-protected and transactional; candidate slots are read-only.

## Explainable Duration Recommendation

- **Scenario:** a user asks for a duration suggestion for one task after recording real execution evidence.
- **Rule boundary:** explicit project/first-tag buckets take precedence; a versioned deterministic bilingual taxonomy may classify title/project/tags into a semantic segment, but returns `unclassified`/`ambiguous` rather than guessing. A segment needs at least three samples and otherwise falls back to the versioned global profile. Evidence is time-decayed and suggestions expire.
- **Failure:** disabled learning returns the original/default estimate with a machine-readable reason; missing or foreign tasks return 404; insufficient evidence never invents confidence; task-level accept/too-short/too-long feedback never shadows a global disable/override decision.
- **Acceptance:** the response exposes classification, feature version, expiry, decay policy, source, sample count, confidence, fallback reason and evidence; Web and Capacitor write the same accurate/too-short/too-long/disable contract; segment feedback affects only its matching segment; temporal-holdout evaluation reports explicit and semantic segment baselines, calibration bins/error or `insufficient_data`.

## Evening Briefing and Temporal Insights

- **Scenario:** at a user-configured local evening time, the system summarizes facts and surfaces high-value deadline risks.
- **Rule boundary:** detector, quiet hours, quota, cooldown, deduplication, and notification creation are deterministic; LLM editing is optional future work.
- **Failure:** expired, dismissed, actioned, or false-positive insights are not reopened; scheduler retries do not duplicate deliveries; notification provider failure remains in delivery state; disabled kinds are neither listed nor newly materialized.
- **Acceptance:** insight scan is bounded and user-scoped; approved decisions create idempotent `NotificationDelivery` facts with an owned insight deep link; each insight source/channel pair has at most one immutable delivery fact, payload contract changes use a versioned idempotency key, and a legacy delivery is retained rather than rewritten or duplicated; independent inbox/detail routes expose the same states as Today; chat continuation resolves evidence through Tools; dismiss/action/false-positive cancels deliveries that have not started sending through `NotificationService`; false-positive feedback may explicitly disable only that insight kind and is idempotently escalatable; evening briefing uses the same fact sources; guardrail evaluation requires an explicit window and declared thresholds and computes false-positive rate over generated insights.

## Controlled Local Replan

- **Scenario:** a blocked interval affects explicitly movable tasks and the user reviews a minimal change before execution.
- **Rule boundary:** preview is read-only; mutation requires an enabled `AutomationPolicy`, explicit reschedule consent, a move cap, task-version checks, and an auditable `ScheduleChangeBatch`. Direct API execution is limited to policies with `requires_approval=false`; Agent execution is a high-risk Tool and must resume through ActionProposal/HITL approval. Background dispatch additionally requires a non-empty, ownership-validated Task allowlist.
- **Failure:** stale tasks, reused operation IDs with another policy, current schedule conflicts, policy violations, and changed-after-apply tasks fail closed; revert refuses to overwrite later edits.
- **Acceptance:** deterministic disruption detection reports exact Task/Event overlaps without mutation; apply recomputes the preview from PostgreSQL facts, proposed moves do not overlap, preview exposes movement-distance cost, policies can pause/resume and update an object allowlist, repeated operation IDs are idempotent, the Celery dispatcher stays within allowlist/cap, before/after snapshots are persisted, revert restores the prior schedule through `TaskService`, unspecified tasks never move, and a mid-batch database failure rolls back every local write. Time Memory may summarize accepted/reverted/user-modified moves but cannot expand autonomy.

## Evaluation Contract

- `benchmark_planning` emits a stable baseline and candidate comparison structure.
- `benchmark_time_memory --user-id` uses a temporal holdout and emits `insufficient_data` when evidence is inadequate.
- `benchmark_adaptive_planning` compares movement count/distance and deadline/overlap feasibility against a deterministic full-compaction baseline.
- `evaluate_insight_guardrails` computes action/dismiss/delivery outcomes only for an explicit observation window and never passes undeclared guardrails.
- `real-backend.spec.ts` is opt-in and must run against a disposable database; it must not register Playwright API route mocks or reuse production data.
- No metric is presented as a product result until a real dataset run is stored with its command, environment, and timestamp.
