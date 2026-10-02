# Tool Routing / Tool Discovery Evolution (2026-10-02)

## Decision

Keep `regex_pack` as the production default. The experiment does not support promoting LLM selection, lexical retrieval, or retrieval plus selection: the best candidate, BM25 Top-8, completed 26/36 trials (72.2%) versus 30/36 (83.3%) for the baseline. BM25 Top-8 improved required-tool exposure recall over Top-4/6, but mean required-tool execution recall was 58.3% across the 24 applicable trials, versus 83.3% for the baseline. It also had a 33.3% tool-surface mismatch rate and an 11.1% duplicate-draft rate.

The new strategies remain configuration options for further controlled experiments. No embedding service, vector database, provider-native search dependency, new Agent, or public API was added. The primary runtime remains one LangChain `create_agent()` Time Steward with the existing LangGraph, ActionProposal/HITL, and application-service boundaries.

The experiment exposed and fixed one deterministic policy bug: the English request “Please remember that …” was treated as read-only, preventing the memory write tool from being selected. The routing regression is covered by unit tests. This correction is included in the reported supplemental memory case.

## Current architecture review

The manifest currently contains **45 tools in 15 packs**. `PACK_TOOL_NAMES` remains the regex baseline and compatibility map; `TOOL_MANIFEST`/`TOOL_SPECS` supplies the shared runtime catalog. Tool visibility is never treated as permission to execute.

| Pack | Tools |
|---|---|
| `overview` | `list_events`, `list_reminders`, `list_tasks` |
| `calendar` | `create_recurring_event`, `get_event`, `list_events`, `mutate_events` |
| `tasks` | `cancel_task`, `change_task_batch_state`, `change_task_state`, `complete_task`, `create_task`, `create_task_batch`, `get_task`, `get_task_execution_summary`, `list_tasks`, `reschedule_task`, `update_task` |
| `reminders` | `cancel_reminder`, `create_reminder`, `get_reminder`, `list_reminders`, `set_reminder_target`, `update_reminder` |
| `availability` | `get_planning_context` |
| `clock` | `get_current_datetime` |
| `planning_preview` | `get_planning_context`, `propose_schedule_plan` |
| `plan_comparison` | `compare_schedule_plans` |
| `duration_guidance` | `recommend_task_duration` |
| `plan_review` | `abandon_schedule_plan`, `apply_schedule_plan`, `edit_schedule_plan`, `get_planning_context`, `request_plan_interaction`, `validate_schedule_plan` |
| `plan_adaptation` | `detect_schedule_disruptions`, `get_planning_context`, `get_task`, `reschedule_task` |
| `automation_replan` | `apply_local_replan`, `detect_schedule_disruptions`, `get_planning_context`, `list_automation_policies` |
| `time_insights` | `act_on_temporal_insight`, `forget_time_preference`, `get_capacity_forecast`, `get_task_execution_summary`, `get_temporal_insight`, `list_temporal_insights`, `recommend_task_duration`, `record_task_duration_feedback`, `remember_time_preference`, `search_time_memories`, `update_time_preference` |
| `integrations` | `list_calendar_sync_status` |
| `briefing_handoff` | `transfer_to_briefing` |

`_PACK_INTENTS` maps request phrases to one or more packs; `select_tool_names()` unions their tools, applies special cases for read-only requests, calendar/task mutation, planning, availability, and multi-task requests, and returns `None` when intent is unclear or too broad. `should_limit_to_read_tools()` independently classifies read-only intent. In multi-task scheduling, the deterministic request policy removes `reschedule_task` from the hard-allowed set.

The new `ToolSpec` catalog carries tool domain/effect, packs, run modes, approval and audit risk metadata, retry safety, idempotency, searchable/eager flags, search keywords, and lifecycle phases. Tool descriptions remain on the registered LangChain tools; the pack map and HITL metadata remain in `tool_metadata.py`. There are no permanently eager tools by default (`DEFAULT_ALWAYS_EAGER_TOOL_NAMES` is empty). Configurable `always_include` is intersected with the authorized and lifecycle-visible set.

`resolve_request_policy()` deterministically checks the authenticated actor, sensitive/cross-user requests, read-only intent, multi-task safety, and Memory feature flags. `hard_allowed_tools` is the execution candidate set. `visible_tools` is the model-facing set after discovery. The selector and retriever only receive the hard-allowed set, further restricted by the planning lifecycle phase.

`ToolPolicyMiddleware` filters the model request and checks every tool call before its handler runs. If a model requests a tool outside the exact recorded selected surface, it returns `tool_surface_mismatch`; if the tool is outside hard policy it returns `tool_not_authorized`. A recovery candidate cannot widen a previously recorded non-null surface. HITL only runs after this deterministic authorization check. Business services still enforce ownership, versions, conflicts, idempotency, and domain rules.

The lifecycle hint is derived from successful tool messages in the **current user turn**. After a plan draft, proposal/comparison tools leave the principal surface while edit, validate, apply, abandon, and planning context remain available. This is discovery guidance only; lifecycle state does not grant execution permission.

Middleware order in `build_time_steward_middleware()` is: runtime prompt and memory/context middleware; untrusted tool data; deterministic tool policy; HITL and auditing; model/tool limits and fallback/retry; optional LangChain selector; final selected-surface recording; tool retry/error handling; summarization and usage telemetry. This keeps policy before discovery and execution authorization in the tool-call path.

The DeepSeek path uses the OpenAI-compatible LangChain adapter and an explicit function-calling structured-output wrapper for the selector. The tested main model was `deepseek-v4-flash`. The repository also configures Claude through LangChain's Anthropic provider adapter, but Claude was not run in this experiment. No claim is made that DeepSeek supports provider-native Tool Search.

## External implementation research

| Project | Relevant design | TimeAgent consequence |
|---|---|---|
| [LangChain middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in) | `LLMToolSelectorMiddleware` selects from the tool schemas it receives; `max_tools` bounds the result and `always_include` bypasses selection. Provider tool search has model/provider constraints. | Reuse the existing middleware. Run deterministic policy first, record its resulting surface, and keep provider-native search out of the portable core. |
| [Pydantic AI toolsets](https://pydantic.dev/docs/ai/tools-toolsets/toolsets/) and [advanced tools](https://pydantic.dev/docs/ai/tools-toolsets/tools-advanced/) | Filtered/dynamic/deferred toolsets, local search fallback, and approval-required wrappers separate loading from authorization. | Keep filtering, discovery, and approval as separate responsibilities; provider-independent retrieval is a valid fallback. |
| [Letta tools](https://docs.letta.com/api/python/resources/tools) | Tool metadata can be searched with lexical/full-text/vector or hybrid ranking before full schemas are loaded. | Use a small metadata catalog and schema exposure as the retrieval reference; 45 tools do not justify a vector store. |
| [Microsoft Agent Framework tool availability](https://learn.microsoft.com/en-us/agent-framework/agents/tools/controlling-tool-availability) | Per-invocation add/remove and progressive MCP exposure can follow runtime phase. | Apply deterministic lifecycle state before selection, rather than asking retrieval to infer plan phase. |
| [OpenAI Agents SDK tools](https://openai.github.io/openai-agents-python/tools/) and [tool reference](https://openai.github.io/openai-agents-python/ref/tool/) | Deferred search, namespaces, filters, approval, and guardrails are distinct tool controls. | Tool search is not authorization; execution policy and HITL stay in trusted code. |
| [DeepAgents skills](https://docs.langchain.com/oss/python/deepagents/skills) | Metadata-first progressive disclosure loads detailed capability content on demand. | Keep compact metadata available for retrieval and expose the complete schema only for the selected capability. |
| [Google ADK callbacks and context](https://adk.dev/callbacks/types-of-callbacks/) | A before-tool callback receives the tool, arguments, and tool context; it can skip the handler before execution. | Use runtime context for deterministic filtering and retain execution checks as a separate boundary. |
| [browser-use parameters](https://docs.browser-use.com/open-source/customize/agent/all-parameters) | Its agent configuration and browser/session context are runtime inputs to browser actions. | Treat page/workflow state as an input to discovery; do not let the selector invent permissions. |

## Tool discovery implementation

Four strategies are configurable in `tool_discovery` and injectable for experiments:

1. `regex_pack`: preserved baseline.
2. `llm_selector`: LangChain `LLMToolSelectorMiddleware` over the policy-filtered tool list.
3. `lexical_retrieval`: deterministic in-process BM25-style ranking over tool name, description, domain, packs, and keywords.
4. `retrieval_plus_llm`: BM25 Top-8/Top-10 followed by the LangChain selector Top-4/Top-6.

Retrieval uses English tokenization and overlapping Chinese character n-grams, has deterministic tie breaking, and falls back conservatively if lexical ranking returns no match. The current default remains `regex_pack`; the example configuration does not turn on a candidate strategy. Enabling an LLM selector now requires an explicit configured selector model alias or an injected selector model, preventing silent fallback to the main model in production configuration.

The experiment used the same DeepSeek alias for the primary model and selector because no separate cheaper selector model was available in the evaluation setup. This does not satisfy the desired low-cost-selector comparison; it is a limitation and another reason not to promote B or D.

## Experiment design

- Fixture: 12 Chinese/English cases covering explicit/vague/paraphrased planning, read-only intent, exact 21:00 edit, apply/HITL, memory write/HITL, availability, cross-domain clarification, cross-user isolation, and conflicting write intent.
- Anchor: `2026-10-05T00:00:00Z`, `Asia/Shanghai`; each trial used a synthetic account and isolated task data.
- Model: `deepseek-v4-flash`, temperature 0, provider retries 0, middleware retries 2; selector uses the same alias in B/D.
- Repeats and order: 3 repeats per scenario, with strategy order randomized per scenario/repeat from seed `20261002`.
- Conditions: A (1), B Top-4/6/8 (3), C Top-4/6/8/10 (4), D Top-8 or Top-10 then selector Top-4/6 (4): 12 conditions × 12 scenarios × 3 repeats = 432 trial rows.
- Isolation: evaluation ran against the local evaluation PostgreSQL/Redis containers, not production. Synthetic trial users and their records were deleted after each run.
- Cost estimate: fixed evaluator rates of USD 0.30/M input tokens and USD 1.20/M output tokens for both calls. This is a comparative estimate, not a provider invoice; see [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/).
- Repeatability limits: prompts, anchor, fixture hash, model alias, temperature, retry policy, random order, and evaluation database are recorded. Provider responses are nondeterministic; the provider did not expose a reproducible model revision or seed in these artifacts.

The first 432-row attempt accidentally ran with semantic-memory search/write flags disabled. Those 36 memory rows are preserved in the `*-initial-before-memory-correction.json` artifacts but were excluded from the primary result. The supplemental 36-row run enabled search, write, and inline-HITL settings, fixed the English memory-intent classifier, used seed `20261608`, and verified that its per-repeat variant order exactly matched the original schedule. Those rows replace the invalid memory rows in the primary raw and blind-trajectory files. The pre-fix diagnostic rerun artifacts remain in the directory and are not part of the aggregate.

## Primary results

Task success is the main outcome. Required-tool recall is the mean fraction of expected tool calls successfully observed across the 24 runs per condition whose fixture specified at least one required tool; a model-call exception without an observed successful required call counts as zero. Selector precision/recall describes schema exposure, not task execution. Tool-call and safety rates use only complete recorded trajectories; their coverage is shown separately. Main-model and selector token means use trials with complete usage for that component. Combined token and cost means require complete usage for all calls in the trial.

| Condition | Success / 36 | Required-tool recall (24 applicable runs) | Selected recall | Allowed precision (coverage) | Wrong tool rate (coverage) | Forbidden calls (trajectory coverage) | Surface mismatch | HITL round trip / 6 | Failed runs / 36 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A Regex | 30 (83.3%) | 83.3% | 100.0% | 98.3% (83.3%) | 1.4% (100%) | 0 (100%) | 0.0% | 5 (83.3%) | 0 |
| B LLM Top-4 | 6 (16.7%) | 8.3% | 29.2% | 79.6% (25.0%) | 15.3% (33.3%) | 0 (33.3%) | 8.3% | 0 (0%) | 24 |
| B LLM Top-6 | 6 (16.7%) | 8.3% | 16.7% | 72.2% (16.7%) | 18.5% (25.0%) | 0 (25.0%) | 11.1% | 0 (0%) | 27 |
| B LLM Top-8 | 21 (58.3%) | 54.2% | 64.6% | 94.8% (66.7%) | 4.6% (75.0%) | 0 (75.0%) | 0.0% | 1 (16.7%) | 9 |
| C BM25 Top-4 | 25 (69.4%) | 56.3% | 91.7% | 98.3% (83.3%) | 1.4% (100%) | 0 (100%) | 22.2% | 3 (50.0%) | 0 |
| C BM25 Top-6 | 25 (69.4%) | 54.2% | 93.8% | 100% (83.3%) | 0.0% (100%) | 0 (100%) | 25.0% | 3 (50.0%) | 0 |
| C BM25 Top-8 | 26 (72.2%) | 58.3% | 97.9% | 96.7% (83.3%) | 2.8% (100%) | 0 (100%) | 33.3% | 4 (66.7%) | 0 |
| C BM25 Top-10 | 22 (61.1%) | 45.8% | 100% | 95.3% (88.9%) | 4.2% (100%) | 0 (100%) | 33.3% | 2 (33.3%) | 0 |
| D BM25-8 + LLM-4 | 15 (41.7%) | 29.2% | 70.8% | 85.4% (66.7%) | 13.0% (75.0%) | 0 (75.0%) | 14.8% | 0 (0%) | 9 |
| D BM25-8 + LLM-6 | 12 (33.3%) | 12.5% | 62.5% | 83.3% (50.0%) | 12.5% (66.7%) | 0 (66.7%) | 4.2% | 0 (0%) | 12 |
| D BM25-10 + LLM-4 | 13 (36.1%) | 20.8% | 64.6% | 85.7% (58.3%) | 12.5% (66.7%) | 0 (66.7%) | 16.7% | 0 (0%) | 12 |
| D BM25-10 + LLM-6 | 12 (33.3%) | 14.6% | 64.6% | 85.0% (55.6%) | 12.0% (69.4%) | 0 (69.4%) | 4.0% | 0 (0%) | 11 |

| Condition | Mean visible tools | Agent steps | Tool calls (coverage caveat) | Selector calls | p50 / p95 seconds | Main input/output/total tokens per task (main-token coverage) | Selector input/output/total tokens per task (selector-token coverage) | Cost/task (coverage) | Duplicate draft rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A Regex | 9.60 | 2.86 | 1.97 | 0 | 3.40 / 7.76 | 28,313 / 400 / 28,713 (100%) | N/A (no selector calls) | $0.00897 (100%) | 0.0% |
| B LLM Top-4 | 0.92 | 0.75 | 1.25 (33%) | 4.75 | 11.41 / 14.86 | 16,713 / 255 / 16,968 (39%) | 10,331 / 391 / 10,723 (100%) | $0.00735 (33%) | 0.0% |
| B LLM Top-6 | 0.72 | 0.56 | 1.22 (25%) | 5.00 | 11.80 / 13.19 | 17,605 / 295 / 17,900 (28%) | 11,118 / 421 / 11,539 (100%) | $0.00738 (25%) | 0.0% |
| B LLM Top-8 | 4.15 | 1.94 | 1.96 (75%) | 3.64 | 8.78 / 13.60 | 22,995 / 394 / 23,389 (78%) | 7,964 / 260 / 8,224 (100%) | $0.00963 (75%) | 0.0% |
| C BM25 Top-4 | 5.90 | 2.67 | 1.64 | 0 | 3.21 / 8.02 | 22,571 / 336 / 22,907 (100%) | N/A (no selector calls) | $0.00717 (100%) | 8.3% |
| C BM25 Top-6 | 7.47 | 2.61 | 1.64 | 0 | 2.78 / 7.10 | 23,132 / 340 / 23,473 (100%) | N/A (no selector calls) | $0.00735 (100%) | 16.7% |
| C BM25 Top-8 | 8.93 | 2.94 | 2.00 | 0 | 3.59 / 8.80 | 27,981 / 378 / 28,359 (100%) | N/A (no selector calls) | $0.00885 (100%) | 11.1% |
| C BM25 Top-10 | 10.44 | 2.78 | 1.83 | 0 | 3.13 / 8.45 | 26,881 / 360 / 27,242 (100%) | N/A (no selector calls) | $0.00850 (100%) | 16.7% |
| D BM25-8 + LLM-4 | 1.87 | 2.47 | 2.30 (75%) | 3.97 | 6.87 / 15.25 | 25,561 / 402 / 25,962 (78%) | 4,465 / 221 / 4,686 (100%) | $0.00948 (75%) | 22.2% |
| D BM25-8 + LLM-6 | 2.34 | 2.06 | 2.00 (67%) | 4.06 | 6.79 / 17.13 | 22,175 / 321 / 22,496 (75%) | 4,577 / 280 / 4,857 (100%) | $0.00858 (67%) | 25.0% |
| D BM25-10 + LLM-4 | 1.81 | 2.47 | 2.71 (67%) | 4.44 | 11.28 / 16.37 | 28,265 / 460 / 28,724 (72%) | 5,178 / 270 / 5,448 (100%) | $0.01089 (67%) | 25.0% |
| D BM25-10 + LLM-6 | 2.28 | 2.11 | 2.00 (69%) | 4.06 | 8.70 / 17.36 | 23,588 / 337 / 23,925 (72%) | 4,665 / 281 / 4,947 (100%) | $0.00866 (69%) | 24.0% |

Selected-tool precision, selector latency percentiles, and every metric denominator are retained in the raw artifact's per-condition summaries. `B`/`D` main-model token means use only trials with complete main-model usage; selector token means use all trials with complete selector usage. Combined token and cost means have lower coverage because they require usage data for every call in the trial, so they do not establish that a successful task would cost less.

### Case-level results

- Baseline exact 21:00 edit and Apply/HITL each passed 3/3. No dynamic candidate matched both: BM25 Top-4 passed exact edit 2/3, BM25 Top-10 1/3, and BM25 Top-8 passed Apply/HITL 2/3; other tested candidates scored 0/3 on these cases.
- Explicit English plan request: baseline passed 0/3; D BM25-8 + LLM-4 passed 2/3 and D BM25-10 + LLM-4 passed 1/3. This narrow gain did not offset lower suite-wide success, slower p95, and weaker HITL.
- Corrected English memory-write case: baseline 2/3; BM25 Top-4/6 each 3/3; Top-8/10 each 2/3; LLM Top-8 1/3. The other selector/hybrid settings passed 0/3, including model-call failures for several B/D settings.
- Paired task-success comparison across the 36 same-case/repeat trials: C Top-8 beat baseline once, lost five times, and tied 30 times. B Top-8 beat baseline twice, lost 11, and tied 23.

## Independent blind trajectory review

The independent trajectory judge received anonymized conditions and the **11 scenarios from the original blind artifact**; the memory case was excluded because its feature flags were invalid in that run. Scores below are holistic 0–5 ratings, not an objective benchmark. The corrected memory trajectories are in the artifact but were not included in that blind score.

| Blind condition | Strategy | Score / 5 | Non-empty final response / 33 | Judge notes |
|---|---|---:|---:|---|
| condition_12 | A Regex | 4.7 | 33 | Highest completion/correctness; exact-time edit and apply flow worked. |
| condition_06 | B Top-4 | 1.5 | 9 | Many selector/runtime failures. |
| condition_02 | B Top-6 | 1.5 | 9 | Many selector/runtime failures. |
| condition_08 | B Top-8 | 3.5 | 24 | Better completion, but still repetitive and less reliable than baseline. |
| condition_10 | C Top-4 | 3.9 | 33 | Mostly complete; occasional routing mismatch. |
| condition_11 | C Top-6 | 4.0 | 33 | Complete, but some duplicate/extraneous tool use. |
| condition_05 | C Top-8 | 4.0 | 33 | Good surface coverage; exact edits and repeated planning calls remained issues. |
| condition_03 | C Top-10 | 3.6 | 33 | Reliable responses but more repetitive task discovery. |
| condition_04 | D 8 + 4 | 3.1 | 27 | Several failures and extra calls. |
| condition_09 | D 8 + 6 | 2.6 | 24 | Incomplete responses and excess calls. |
| condition_07 | D 10 + 4 | 2.7 | 24 | Incomplete responses and excess calls. |
| condition_01 | D 10 + 6 | 3.0 | 25 | Better than smaller selector variants, still below A/C. |

The judge found no evidence of successful cross-user access or an approved write bypass in the supplied trajectories. This is evidence about the observed fixture set only, not a proof of general safety.

## Security results and known failures

- Across complete recorded trajectories: zero observed forbidden calls and zero observed unauthorized calls. Trace coverage ranged from 25% for B Top-6 to 100% for A and all C variants; the table reports coverage alongside those rates.
- Deterministic execution policy remains authoritative. Hidden unapproved tool-call regression tests assert `tool_not_authorized` or `tool_surface_mismatch` before the tool handler runs. HITL and domain service checks are unchanged.
- Selector/hybrid runs generated 9–27 `AssertionError` failures per configuration; the captured safe error was `Expected dict response, got <class 'NoneType'>`. These rows count as task failures and as zero observed required-tool executions when a required tool was expected; they have no complete tool trajectory and are excluded from call-level error rates.
- Lexical retrieval caused 22–33% tool-surface mismatch rates and 8–17% duplicate-draft rates. Retrieval plus selection had 22–25% duplicate-draft rates on complete trials and the highest p95 latency (15.25–17.36s).
- Error/trajectory/token coverage is explicit in the primary JSON summaries. Never interpret a zero forbidden-call count without its trajectory coverage.

## Decision and migration plan

1. Keep `regex_pack` as the configured/default strategy.
2. Keep BM25 and LangChain selector strategies opt-in and experimental. Do not route production traffic to them based on this evaluation.
3. Retain the new catalog, policy/discovery separation, current-turn lifecycle handling, and selected-surface audit metadata; these are useful independently of whether retrieval is promoted.
4. Require an explicit selector-model alias for selector strategies. A future selector evaluation should use a distinct lower-cost model, larger blinded holdouts, and repeated exact-time/HITL cases before reconsidering B or D.
5. Improve lexical metadata/matching only against recorded failure cases, then repeat the same fixture without cherry-picking. Address the 21:00 and Apply/HITL cases before considering promotion.
6. Reconsider embeddings only if lexical paraphrase misses remain the measured bottleneck. No vector database or embedding dependency is justified now.

## Rejected alternatives

- **Replace regex with LLM selection:** rejected by much lower task success (16.7–58.3%), frequent model-call errors, and no improvement in HITL round trips.
- **Promote BM25 Top-8 because selected recall is high:** rejected because 97.9% surface recall produced only 58.3% required-tool execution recall and 72.2% task success, with 33.3% mismatch.
- **Promote retrieval plus reranking because it creates the smallest surface:** rejected because it had 33.3–41.7% task success, 0/6 HITL round trips across settings, high duplicate drafts, and the slowest p95.
- **Add embeddings/pgvector:** rejected because the local lexical baseline did not beat the existing router and 45 tools are a small catalog.
- **Use provider-native search as the core path:** rejected because its model/provider constraints conflict with DeepSeek/Claude portability.
- **Rename public tool names or split the Agent runtime:** rejected because current names are API/runtime compatibility points and the experiment gives no reason to add a router or second Agent.

## Artifacts

- Primary full raw results, including replaced supplemental rows: [`artifacts/tool-discovery-evolution-2026-raw.json`](artifacts/tool-discovery-evolution-2026-raw.json)
- Primary anonymized trajectories: [`artifacts/tool-discovery-evolution-2026-blind-trajectories.json`](artifacts/tool-discovery-evolution-2026-blind-trajectories.json)
- Original raw and blind runs before the memory-case correction: `artifacts/tool-discovery-evolution-2026-raw-initial-before-memory-correction.json` and `artifacts/tool-discovery-evolution-2026-blind-trajectories-initial-before-memory-correction.json`
- Corrected memory-only raw and blind runs: `artifacts/tool-discovery-evolution-2026-memory-hitl-policy-fix-raw.json` and `artifacts/tool-discovery-evolution-2026-memory-hitl-policy-fix-blind-trajectories.json`
- Earlier diagnostic memory attempts are retained for audit but excluded from the primary aggregate.
- Dataset: [`backend/tests/fixtures/tool_discovery_eval.json`](../../backend/tests/fixtures/tool_discovery_eval.json), SHA-256 `f885c5d4a2dda698046a5a77b41aeaa6dbb84a2abb8eaf68865e9d1ec03aa2bd`.
