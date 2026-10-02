# ADR 0035: Policy-First Tool Discovery

- Status: Accepted; alternative discovery strategies remain experimental
- Date: 2026-10-02

## Context

Time Steward currently exposes a request-specific subset of a 45-tool catalog. As the catalog grows, semantic retrieval or model-based selection could reduce schema size and improve paraphrase coverage. Schema visibility is not authorization, however, and discovery must respect actor identity, read-only mode, memory consent, planning lifecycle, and HITL policy. A strategy should not replace the established router without evidence from representative, repeated model runs.

## Decision

1. Keep `regex_pack` as the configured production default. Add opt-in `llm_selector`, lexical BM25-style retrieval, and retrieval-plus-selector strategies behind the same discovery boundary.
2. Resolve deterministic request policy first. Discovery receives only `hard_allowed_tools`, then applies lifecycle filtering. The final model-visible surface is recorded on the assistant response and checked again before tool execution.
3. Keep visibility and execution authorization separate. A selected surface cannot widen hard policy; recovery cannot widen a previously recorded non-null surface. Ownership, domain validation, idempotency, and HITL remain enforced by existing trusted services and middleware.
4. Use the existing `TOOL_SPECS` manifest as the shared catalog. Keep registered tool names and the single LangChain `create_agent()` Time Steward stable. Do not add embeddings, a vector database, a new Agent, or provider-native search without measured evidence.
5. LLM selector strategies require an explicit configured selector-model alias or an injected selector model. They must not silently fall back to the primary model in production configuration.
6. Promote a strategy only after repeatable real-model evaluation on the regression fixture and fresh blinded hold-outs, including exact-time edits, Apply/HITL, memory consent, safety, latency, and token/cost coverage. Failed or incomplete traces count against task success; safety rates must report trace coverage.

## Evidence

The 2026-10-02 experiment ran 432 trials across 12 conditions, 12 scenarios, and three repeats, with a corrected supplemental run for the memory scenario. On the current fixture, the regex baseline completed 30/36 tasks (83.3%). The strongest candidate, BM25 Top-8, completed 26/36 (72.2%) and had lower mean required-tool recall, 58.3% across the 24 applicable trials, plus a 33.3% surface-mismatch rate. Selector and hybrid conditions had repeated model-call failures and weaker Apply/HITL completion. See [the experiment report](../experiments/tool-discovery-evolution-2026.md) and its raw artifacts for method, coverage, blind trajectory review, and limitations.

## Consequences

- Discovery can evolve independently while the production default remains stable.
- Every candidate still has to operate within deterministic policy and lifecycle boundaries.
- Current results justify retaining the manifest and experiment harness, but do not justify promoting retrieval or selector strategies.
- Evaluation results are model-version-sensitive; the provider did not expose a reproducible model revision or seed for these runs. Future comparisons should use a distinct lower-cost selector model and fresh hold-outs.

## Alternatives considered

- Replace the router with LLM selection: rejected due to lower task completion and frequent selector failures.
- Promote lexical Top-8 based on its high selected-tool recall: rejected because tool exposure did not translate into required-tool execution or overall task success.
- Use lexical retrieval followed by an LLM selector: rejected due to low completion, no successful HITL round trips, duplicate drafts, and higher tail latency.
- Add embeddings/vector search or provider-native search: deferred because the measured lexical candidate did not beat the baseline, the current catalog is small, and provider portability matters.
