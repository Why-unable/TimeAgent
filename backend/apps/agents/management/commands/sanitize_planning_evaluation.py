"""Export planning evaluator reports as privacy-safe, reproducible artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.agents.tools import TOOL_SPECS

SCHEMA_VERSION = "timeagent.sanitized-evaluation-runs.v1"
TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
ARG_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
DATETIME_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[+-]\d\d:\d\d)$")


def _opaque_case_id(value: object) -> str:
    return f"case_{hashlib.sha256(str(value).encode('utf-8')).hexdigest()[:16]}"


def _safe_code(value: object) -> str:
    raw = str(value).split(":", maxsplit=1)[0].casefold()
    normalized = re.sub(r"[^a-z0-9_]+", "_", raw).strip("_")
    normalized = normalized[:64]
    return normalized if normalized and normalized[0].isalpha() else "evaluation_error"


def _redact_argument(value: Any, *, key: str = "") -> Any:
    if isinstance(value, dict):
        return {
            str(child_key): _redact_argument(child, key=str(child_key))
            for child_key, child in value.items()
            if ARG_KEY_RE.fullmatch(str(child_key))
        }
    if isinstance(value, list):
        return [_redact_argument(child, key=key) for child in value]
    if isinstance(value, str):
        return "[redacted:datetime]" if DATETIME_RE.fullmatch(value) else "[redacted:string]"
    if key.casefold().endswith("_id") or key.casefold() == "id":
        return "[redacted:id]"
    if value is None or isinstance(value, bool | int | float):
        return value
    return "[redacted:value]"


def _safe_tool_calls(raw_calls: object) -> list[dict[str, Any]]:
    if not isinstance(raw_calls, list):
        return []
    calls: list[dict[str, Any]] = []
    for raw in raw_calls:
        if not isinstance(raw, dict):
            continue
        raw_name = str(raw.get("name", ""))
        name = raw_name if raw_name in TOOL_SPECS else "unknown_tool"
        status = raw.get("status")
        if status not in {"success", "error", "unknown"}:
            status = "unknown"
        arguments = raw.get("arguments", {})
        calls.append(
            {
                "name": name,
                "status": status,
                "arguments_redacted": _redact_argument(arguments)
                if isinstance(arguments, dict)
                else {},
            }
        )
    return calls


def _safe_schedule(raw_plans: object) -> list[dict[str, Any]]:
    if not isinstance(raw_plans, list):
        return []
    candidates: list[dict[str, Any]] = []
    for candidate_index, raw_plan in enumerate(raw_plans, start=1):
        if not isinstance(raw_plan, dict):
            continue
        raw_schedule = raw_plan.get("schedule", {})
        schedule: list[dict[str, Any]] = []
        if isinstance(raw_schedule, dict):
            for task_index, task_key in enumerate(sorted(raw_schedule), start=1):
                raw_segments = raw_schedule[task_key]
                segments: list[dict[str, Any]] = []
                if isinstance(raw_segments, list):
                    for segment in raw_segments:
                        if not isinstance(segment, dict):
                            continue
                        start_at = segment.get("start_at")
                        end_at = segment.get("end_at")
                        if not isinstance(start_at, str) or not isinstance(end_at, str):
                            continue
                        if not DATETIME_RE.fullmatch(start_at) or not DATETIME_RE.fullmatch(end_at):
                            continue
                        segments.append({"start_at": start_at, "end_at": end_at})
                if segments:
                    schedule.append({"task_id": f"task_{task_index:02d}", "segments": segments})
        checks = raw_plan.get("soft_checks", [])
        soft_passed = 0
        soft_count = 0
        safe_checks: list[dict[str, Any]] = []
        if isinstance(checks, list):
            for check in checks:
                if not isinstance(check, dict) or not isinstance(check.get("passed"), bool):
                    continue
                safe_checks.append(
                    {"code": _safe_code(check.get("name", "unknown")), "passed": check["passed"]}
                )
                soft_count += 1
                soft_passed += int(check["passed"])
        violations = raw_plan.get("hard_violations", [])
        candidates.append(
            {
                "candidate_index": candidate_index,
                "status": _safe_code(raw_plan.get("status", "unknown")),
                "task_count": _nonnegative_int(raw_plan.get("task_count")),
                "placed_task_count": _nonnegative_int(raw_plan.get("placed_task_count")),
                "unplaced_task_count": len(raw_plan.get("unplaced_task_keys", []))
                if isinstance(raw_plan.get("unplaced_task_keys"), list)
                else 0,
                "placed_minutes": _nonnegative_int(raw_plan.get("placed_minutes")),
                "placed_segments": _nonnegative_int(raw_plan.get("placed_segments")),
                "distinct_day_count": len(raw_plan.get("distinct_days", []))
                if isinstance(raw_plan.get("distinct_days"), list)
                else 0,
                "distinct_week_count": len(raw_plan.get("distinct_weeks", []))
                if isinstance(raw_plan.get("distinct_weeks"), list)
                else 0,
                "schedule": schedule,
                "hard_violations": sorted(
                    {_safe_code(item) for item in violations}
                    if isinstance(violations, list)
                    else set()
                ),
                "soft_check_pass_rate": _finite_rate(raw_plan.get("soft_check_pass_rate")),
                "soft_checks": safe_checks,
            }
        )
    return candidates


def _nonnegative_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _finite_rate(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return round(float(value), 6)
    return None


def _prompt_breakdown(raw: object) -> dict[str, int]:
    keys = (
        "system_prompt_tokens",
        "behavioral_memory_tokens",
        "semantic_memory_tokens",
        "memory_context_tokens",
        "tool_schema_tokens",
        "conversation_tokens",
        "tool_observation_tokens",
        "unattributed_input_tokens",
    )
    source = raw if isinstance(raw, dict) else {}
    return {key: _nonnegative_int(source.get(key)) for key in keys}


class Command(BaseCommand):
    help = "Sanitize full planning evaluation reports into shareable structured artifacts."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--input", action="append", required=True, dest="inputs")
        parser.add_argument("--output", required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        del args
        input_paths = [Path(value).expanduser().resolve() for value in options["inputs"]]
        output_path = Path(options["output"]).expanduser().resolve()
        if output_path in input_paths:
            raise CommandError("Output path must differ from every input path")

        reports: list[dict[str, Any]] = []
        for path in input_paths:
            try:
                report = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise CommandError("Evaluation input could not be read as UTF-8 JSON") from exc
            if (
                not isinstance(report, dict)
                or report.get("schema_version") != "timeagent.planning-harness-evaluation.v1"
                or not isinstance(report.get("results"), list)
            ):
                raise CommandError("Input is not a supported planning evaluation report")
            reports.append(report)

        all_case_ids = sorted(
            {
                str(row.get("scenario_id", ""))
                for report in reports
                for row in report["results"]
                if isinstance(row, dict) and row.get("scenario_id")
            }
        )
        case_ids = {source: _opaque_case_id(source) for source in all_case_ids}
        seen: set[tuple[str, str, int]] = set()
        runs: list[dict[str, Any]] = []
        for report in reports:
            for row in report["results"]:
                if not isinstance(row, dict):
                    continue
                case_id = str(row.get("scenario_id", ""))
                variant = str(row.get("variant", ""))
                surface = row.get("tool_surface")
                if variant == "agent" and surface in {"standard", "compact"}:
                    variant = f"candidate_{surface}"
                repeat = _nonnegative_int(row.get("repeat"))
                key = (case_ids.get(case_id, _opaque_case_id(case_id)), variant, repeat)
                if key in seen:
                    raise CommandError("Duplicate case / variant / repeat rows found")
                seen.add(key)
                plans = _safe_schedule(row.get("plans"))
                run_hard_violations = (
                    {
                        _safe_code(item)
                        for item in row.get("hard_violations", [])
                        if isinstance(item, str)
                    }
                    if isinstance(row.get("hard_violations", []), list)
                    else set()
                )
                run_hard_violations.update(
                    code for plan in plans for code in plan["hard_violations"]
                )
                soft_rates = [
                    plan["soft_check_pass_rate"]
                    for plan in plans
                    if plan["soft_check_pass_rate"] is not None
                ]
                usage = row.get("prompt_breakdown", {})
                usage = usage if isinstance(usage, dict) else {}
                surface_stats = row.get("visible_tool_surface_stats", {})
                surface_stats = surface_stats if isinstance(surface_stats, dict) else {}
                raw_names = surface_stats.get("tool_names_union", [])
                tool_names = (
                    sorted(
                        {
                            name
                            for item in raw_names
                            if isinstance(item, str)
                            for name in [item if item in TOOL_SPECS else "unknown_tool"]
                        }
                    )
                    if isinstance(raw_names, list)
                    else []
                )
                unresolved = row.get("unresolved_tool_errors", [])
                error_categories = (
                    sorted({_safe_code(item) for item in unresolved if isinstance(item, str)})
                    if isinstance(unresolved, list)
                    else []
                )
                top_level_error = row.get("error_type")
                if isinstance(top_level_error, str) and top_level_error:
                    error_categories = sorted({*error_categories, _safe_code(top_level_error)})
                runs.append(
                    {
                        "case_id": key[0],
                        "variant": variant,
                        "repeat": repeat,
                        "passed": bool(row.get("passed")),
                        "duration_seconds": _finite_rate(row.get("duration_seconds")),
                        "hard_violations": sorted(run_hard_violations),
                        "tool_error_count": _nonnegative_int(row.get("tool_error_count")),
                        "unresolved_tool_error_count": len(unresolved)
                        if isinstance(unresolved, list)
                        else 0,
                        "repair_call_count": _nonnegative_int(row.get("repair_call_count")),
                        "accepted": None,
                        "catastrophic": bool(row.get("catastrophic_failure")),
                        "model_call_count": _nonnegative_int(row.get("model_call_count")),
                        "tool_call_count": _nonnegative_int(row.get("tool_call_count")),
                        "duplicate_read_count": _nonnegative_int(row.get("duplicate_read_count")),
                        "total_tokens": _nonnegative_int(row.get("total_tokens")),
                        "model_duration_ms": _nonnegative_int(row.get("model_duration_ms")),
                        "prompt_breakdown_tokens": _prompt_breakdown(usage),
                        "visible_tool_count_mean": _finite_rate(
                            surface_stats.get("mean_tool_count")
                        ),
                        "tool_names": tool_names,
                        "tool_calls": _safe_tool_calls(row.get("tool_trajectory")),
                        "final_schedule": plans,
                        "soft_quality": (
                            round(sum(soft_rates) / len(soft_rates), 6) if soft_rates else None
                        ),
                        "error_categories": error_categories,
                    }
                )

        if not runs:
            raise CommandError("No valid evaluation result rows found")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps({"schema_version": SCHEMA_VERSION, "runs": runs}, indent=2) + "\n",
            encoding="utf-8",
        )
        self.stdout.write(self.style.SUCCESS(f"Wrote {len(runs)} sanitized evaluation runs"))
