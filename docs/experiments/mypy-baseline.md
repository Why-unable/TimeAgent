# Mypy Baseline — V4 Validation

Command: `uv run mypy . --no-error-summary` from `backend/`
Result: **30 findings across 7 existing files**. No Python production files were changed by this V4 UX validation pass.

| Category | File(s) | Findings | Classification |
| --- | --- | ---: | --- |
| Historical interaction ownership/nullability | `apps/interactions/models.py`, `apps/interactions/views.py` | 5 | Nullable related plan/task/conversation/run references are dereferenced without narrowing. |
| Planning | `apps/planning/services.py` | 2 | UUID/string assignment mismatch and missing local annotation for edited item. |
| Agent middleware | `apps/agents/middleware.py` | 1 | Structured output adapter assigned to a model-typed local. |
| Tool discovery evaluator | `apps/agents/management/commands/evaluate_tool_discovery.py` | 19 | CLI/config value narrowing, bool/int generator typing, percentile list variance, object/string TypedDict access, and numeric conversion narrowing. |
| Tests only | `tests/test_interactions.py`, `tests/test_tool_discovery.py` | 3 | `BaseTool.func` attribute typing, missing fixture return annotation, and union access to `.name`. |

No findings were introduced by this pass: the modified production code is TypeScript/React. No `Any`, blanket ignore, or mass cast was added to hide the baseline. These findings are not evidence that changed Python code is type-safe; they are an unchanged baseline and remain follow-up work by their owning area.
