# TimeAgent Tool Architecture Audit and Optimization (2026-09-29)

## Scope and decision

This audit follows `docs/optim/toolset-optim.md` (the requested path `optim/toolset-optim.nd` is absent). The goal is a clearer, safer action space with lower per-request schema cost, not a lower registry count by itself.

Final source candidate manifest: `artifacts/harness-v2-candidate-manifest.json`, SHA-256 `265d62374fe6655f2d1a4d44075e2c3f4343863afb87d0cc8552d4e03d3db3d4` (46 source files).

Keep the 44-tool capability registry for now. Make the **visible surface** narrower by intent and planning phase; keep specialist capabilities available through their own intent packs. One overlapping task-state contract is narrowed, and the clock tool is restricted to explicit clock questions. No capability is removed.

## Current tool map and public-regression usage

The frequency columns come from the prior standard-surface DeepSeek run on 10 synthetic planning scenarios × 3 repeats. `Visible / 30` means the tool appeared at least once in the model-visible schema during a run; `Calls` counts actual tool invocations. This is planning-regression evidence, not a general product-usage study. “Result size” is an engineering estimate because per-tool observation bytes/tokens are not currently persisted.

| Tool | Domain / effect | Schema fields | Visible / 30; calls | Result size | Classification and disposition |
|---|---|---:|---:|---|---|
| `get_current_datetime` | Time / read | 1 | 30 / 24 | Small | Essential specialist; expose in the `clock` pack for explicit current-clock questions. Relative-date decisions already receive the fixed local Runtime anchor in the system message. |
| `list_events` | Calendar / read | 4 | 3 / 0 | Medium to large | Essential collection read; overview/calendar intents only. |
| `get_event` | Calendar / read | 2 | 0 / 0 | Small | Essential item read; keep specialist. |
| `mutate_events` | Calendar / business write, approval policy | 2 | 0 / 0 | Medium | Composite atomic create/update/cancel/link operation; keep as one auditable approval unit. |
| `create_recurring_event` | Calendar / business write, approval policy | 9 | 0 / 0 | Medium to large | Rare specialist; keep separate because recurrence schema and approval scope differ. |
| `list_tasks` | Tasks / read | 3 | 9 / 0 | Medium to large | Essential collection read; hidden on compact planning requests where planning context already supplies task facts. |
| `get_task` | Tasks / read | 2 | 9 / 1 | Small | Essential item read; keep. |
| `get_task_execution_summary` | Tasks / read | 2 | 12 / 0 | Medium | Specialist evidence for duration/progress questions; keep in task/time-insight packs. |
| `create_task` | Tasks / business write | 10 | 6 / 0 | Small to medium | Single-item primitive; keep for low-friction single creation. |
| `create_task_batch` | Tasks / business write, approval policy | 2 | 6 / 0 | Medium | Atomic multi-create; keep separate from single create because approval and batch semantics differ. |
| `update_task` | Tasks / business write | 10 | 6 / 0 | Small | Field updates only; keep separate from lifecycle transitions. |
| `change_task_state` | Tasks / business write | 3 | 6 / 0 | Small | Narrowed to `in_progress` only; do not use for completion or cancellation. |
| `change_task_batch_state` | Tasks / business write, approval policy | 3 | 6 / 0 | Medium | Atomic group completion/cancellation; keep because approval and idempotency are batch-scoped. |
| `complete_task` | Tasks / business write | 2 | 6 / 0 | Small | Keep: records a completion execution signal for duration learning, unlike a generic status update. |
| `reschedule_task` | Tasks / business write, approval policy | 5 | 6 / 3 | Small | Essential explicit single-task move; keep approval-gated. |
| `cancel_task` | Tasks / business write, approval policy | 2 | 6 / 0 | Small | Keep as the only single-task cancellation action; approval is mandatory. |
| `list_reminders` | Reminders / read | 3 | 3 / 0 | Medium | Essential collection read; keep in overview/reminder intents. |
| `get_reminder` | Reminders / read | 2 | 0 / 0 | Small | Essential item read; keep. |
| `create_reminder` | Reminders / business write | 6 | 0 / 0 | Small | Essential primitive; keep. |
| `update_reminder` | Reminders / business write, approval policy | 7 | 0 / 0 | Small | Keep; changing timing/delivery is reviewed. |
| `set_reminder_target` | Reminders / business write, approval policy | 5 | 0 / 0 | Small | Keep; target binding is a distinct reviewed mutation. |
| `cancel_reminder` | Reminders / business write, approval policy | 2 | 0 / 0 | Small | Keep; cancellation is a distinct reviewed action. |
| `get_planning_context` | Planning / read | 12 | 30 / 43 | Large / variable | Core planning read and slot query. It is a broad schema; keep temporarily because repair runs need a fresh context and the two modes both occur. Further context/slot split needs its own A/B before acceptance. |
| `propose_schedule_plan` | Planning / draft | 9 | 30 / 24 | Large | Essential planner decision primitive; creates one reviewable draft, never applies it. Hide after a draft already exists in the current turn. |
| `compare_schedule_plans` | Planning / draft | 9 | 0 / 0 | Large | Rare explicit comparison; keep in the comparison pack and hide after alternatives exist. |
| `detect_schedule_disruptions` | Planning / read | 3 | 3 / 3 | Medium | Essential factual disruption detector; keep for adaptation intents. |
| `list_automation_policies` | Planning / read | 1 | 0 / 0 | Small | Rare specialist authorization read; keep only on automation-replan intent. |
| `validate_schedule_plan` | Planning / derive | 3 | 30 / 0 | Small | Keep in review phase; not used in this particular preview-only benchmark. |
| `edit_schedule_plan` | Planning / draft | 4 | 30 / 0 | Medium | Keep in review phase; atomic versioned plan edits. |
| `abandon_schedule_plan` | Planning / draft | 3 | 30 / 0 | Small | Keep in review phase; explicit draft lifecycle action. |
| `apply_schedule_plan` | Planning / business write, HITL | 3 | 30 / 0 | Small | Keep in review phase; application remains approval-gated. |
| `apply_local_replan` | Planning / business write, HITL | 7 | 0 / 0 | Medium | Rare policy-bounded workflow; keep behind automation-replan intent and HITL. |
| `recommend_task_duration` | Decision / read | 2 | 3 / 0 | Small | Specialist estimate; keep when user asks for duration guidance. |
| `get_capacity_forecast` | Decision / read | 5 | 3 / 0 | Medium | Specialist capacity view; keep when explicitly requested. |
| `record_task_duration_feedback` | Decision / business write | 3 | 3 / 0 | Small | Keep for explicit actual-duration feedback. |
| `list_calendar_sync_status` | Integrations / read | 1 | 0 / 0 | Small | Rare specialist; keep behind integration-status intent. |
| `list_temporal_insights` | Insights / derive | 1 | 3 / 0 | Medium | Specialist insight query; keep. |
| `get_temporal_insight` | Insights / read | 2 | 3 / 0 | Small | Specialist insight detail; keep. |
| `act_on_temporal_insight` | Insights / business write | 5 | 3 / 0 | Small | Specialist action; keep separate from read/derive. |
| `search_time_memories` | Memory / read | 4 | 0 / 0 | Variable | Keep behind memory feature flag and relevant time-insight intent. |
| `remember_time_preference` | Memory / business write, approval policy | 4 | 0 / 0 | Small | Keep; write is proposal/HITL-controlled. |
| `update_time_preference` | Memory / business write, approval policy | 3 | 0 / 0 | Small | Keep; distinct from first-time preference capture. |
| `forget_time_preference` | Memory / business write, approval policy | 2 | 0 / 0 | Small | Keep; explicit deletion remains reviewed. |
| `transfer_to_briefing` | Briefing / handoff | 11 | 0 / 0 | Medium | Specialist handoff; keep on briefing intent only. |

`0 / 0` in this table means the public planning suite did not exercise the capability; it is not evidence that the tool is unused by the product.

## Problems found and changes made

1. **Run anchor was re-read as a tool call.** The prior public regression exposed `get_current_datetime` in all 30 runs and invoked it 24 times, even though the system message already carries the explicit IANA-local run anchor and UTC instant. It now appears in the dedicated `clock` intent pack. Planning, calendar, overview, and adaptation packs rely on the fixed Runtime anchor. The system prompt now calls the tool only when the user asks for the current clock reading. In the final regression it was exposed to no planning runs and invoked zero times; planning-context calls fell from 43 to 31.
2. **Tool surface remained wide after draft creation.** Compact planning now detects a successfully created/compared draft in the current user turn and hides only `propose_schedule_plan` and `compare_schedule_plans`; edit, validate, apply, abandon and `get_planning_context` remain available. The context tool remains visible because an initial phase experiment that also hid it produced a surface-mismatch error when the model needed a fresh availability query to repair edits. The focused case passed 3/3 after retaining context.
3. **Single-task state union overlapped with protected terminal actions.** `change_task_state` accepted arbitrary strings including `cancelled`, while `cancel_task` is approval-gated. The Agent tool now accepts only `in_progress`; completion uses `complete_task` (which records execution feedback), and cancellation uses the approved `cancel_task`. Bulk completion/cancellation remains a separate approval-gated atomic action.
4. **No operation merge based only on names.** Calendar mutations are already consolidated into one atomic `mutate_events` operation with one approval boundary. Task mutations remain separate where audit, idempotency, or approval semantics differ. A broad `mutate_tasks` union would mix low-risk progress, completion signals, cancellation approval, batch writes, and schedule moves; its larger action schema would make policy harder to inspect.
5. **Observation-size instrumentation is incomplete.** Per-tool output token/byte counts and per-model-call exposed-tool sets are not available in sanitized experiment rows. Existing telemetry records aggregate schema/observation token breakdown and per-call visible tool counts. Do not claim per-tool result-size measurements from these runs.

## Tool surface and lifecycle

| Intent / phase | Visible capability shape |
|---|---|
| Clock question | `get_current_datetime` only |
| Agenda overview | Event/task/reminder list reads; no clock call |
| Planning, before a draft | Planning context, one draft proposal, and only intent-relevant supporting reads; broad `list_tasks`/`list_events` and unrelated task writes are hidden in compact mode |
| Planning, after a draft | Context/availability repair plus edit, validation, application, or abandon actions; repeated proposal/comparison is hidden |
| Replan | Disruption detection, planning context, task-scoped availability, and the explicit approval-gated move/policy path |
| Read-only request | Read-only tools only; draft creation and all business writes stay denied by the hard policy |

The registry remains 44 tools; the public standard surface averaged 10.5 visible tools per model call, the first compact candidate averaged 8.3, and the final phase-aware candidate averaged 7.3. The execution policy remains the security boundary; filtering affects the model-facing surface only. The compact planning surface is now the default in `build_time_steward_agent()`.

## A/B evidence

The first same-model comparison used DeepSeek, 10 synthetic public scenarios × 3 repeats, isolated SQLite, and the same final planning prompt. Results:

| Metric | Standard | Compact | Final phase-aware | Interpretation |
|---|---:|---:|---:|---|
| Passed | 30/30 | 30/30 | 30/30 | Same primary pass count |
| Hard violation runs | 0 | 0 | 0 | Equal |
| Tool-error runs / errors | 0 / 0 | 1 / 1 | 0 / 0 | Compact error recovered; none in final |
| Mean visible tools | 10.5 | 8.3 | 7.3 | Final is 30.5% below standard |
| Mean total tokens | 38,531.8 | 35,892.1 | 33,072.9 | Final is 14.2% below standard |
| Tool-schema tokens (sum) | 399,320 | 344,588 | 318,159 | Final is 20.3% below standard |
| Tool-observation tokens (sum) | 231,090 | 214,482 | 179,302 | Final is 22.4% below standard |
| Mean model calls | 3.17 | 3.03 | 2.90 | Final modestly lower |
| Mean tool calls | 3.27 | 3.23 | 2.03 | Final is 37.8% below standard |
| Mean latency | 6.56 s | 7.01 s | 6.43 s | Final mean is slightly lower, but median is 7.01 s vs 6.54 s; latency evidence is mixed |
| Median / worst latency | 6.54 / 10.64 s | 7.14 / 15.81 s | 7.01 / 8.27 s | Final had a lower worst observed run; small sample |
| Mean soft quality | 0.950 | 0.980 | 0.992 | Final improved on this synthetic metric; not a population claim |

The final candidate bundles intent routing, phase-aware hiding of duplicate draft creators, the dedicated clock intent, the corrected Runtime-anchor prompt, and the narrowed single-task state schema. It is not a one-factor experiment, so the aggregate improvements cannot be attributed to any single change. The earlier phase variant that also hid `get_planning_context` was rejected: 29/30 passed, with one run accumulating edit errors after a context surface mismatch. After retaining context, the focused case passed 3/3 (`artifacts/deepseek-tool-phase-focused-20260929-sanitized-runs.json`) and the corrected full candidate passed 30/30. Sanitized comparison: `artifacts/deepseek-tool-architecture-comparison-20260929-summary.json`.

## Final map and next boundary

- **Keep** all current registry capabilities and their service-level implementations.
- **Hide by intent** specialist tools: memory, insights, integrations, briefing, recurrence, automation policy, comparison, duration, and capacity.
- **Hide by phase** only duplicate draft creators after a draft exists; keep context because repair may need a fresh read.
- **Preserve approval boundaries** on schedule application, task cancellation, batch state, event mutation, reminder changes, memory writes, and local replan.
- **Do not merge** task or calendar operations into a giant action union. The existing calendar composite is bounded and atomic; task actions have materially different feedback, state, and approval behavior.
- **Next experiment**: split the overloaded planning read into a small context view and an explicit free-slot query only if the final regression shows lower schema cost without more selection/argument errors. The current 43 planning-context calls include both shapes, so deleting either mode would lose observed behavior.

The final compact phase-aware candidate completed the full public regression at 30/30 with no hard violations or tool errors. Backend verification then passed 624 tests with 3 skipped, Django system check, migration check, Ruff lint, and formatting checks for every changed Python file. Repository-wide `ruff format --check .` still reports 43 pre-existing files needing formatting; those files are outside this change and were left untouched. This document is an audit of a synthetic harness, not a production traffic claim.
