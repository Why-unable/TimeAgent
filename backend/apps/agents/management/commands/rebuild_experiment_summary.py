"""Aggregate privacy-safe planning-harness run exports.

Input files must use ``timeagent.sanitized-evaluation-runs.v1`` and contain only
opaque case IDs, variant/repeat identifiers, scalar outcomes, and violation codes.
This command intentionally does not ingest the full harness report, whose rows may
contain user-facing text, task facts, tool arguments, or memory context.

Example::

    uv run python manage.py rebuild_experiment_summary \
        --input docs/experiments/artifacts/run-a.json \
        --input docs/experiments/artifacts/run-b.json \
        --output docs/experiments/artifacts/summary.json
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from statistics import fmean, median, pvariance
from typing import Any

from django.core.management.base import BaseCommand, CommandError

SCHEMA_VERSION = "timeagent.sanitized-evaluation-runs.v1"
SUMMARY_SCHEMA_VERSION = "timeagent.experiment-summary.v1"
CASE_ID_RE = re.compile(r"^case_[A-Za-z0-9_-]{1,64}$")
VARIANT_RE = re.compile(r"^(?:baseline|agent|candidate_[A-Za-z0-9_-]{1,48})$")
CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
ROOT_KEYS = {"schema_version", "runs"}
RUN_KEYS = {
    "case_id",
    "variant",
    "repeat",
    "passed",
    "duration_seconds",
    "hard_violations",
    "tool_error_count",
    "unresolved_tool_error_count",
    "repair_call_count",
    "accepted",
    "catastrophic",
    "model_call_count",
    "tool_call_count",
    "duplicate_read_count",
    "total_tokens",
    "model_duration_ms",
    "soft_quality",
    "visible_tool_count_mean",
    "prompt_breakdown_tokens",
    "tool_names",
    "tool_calls",
    "final_schedule",
    "error_categories",
}
REQUIRED_RUN_KEYS = {"case_id", "variant", "repeat", "passed"}


def _fail(source: Path, location: str, reason: str) -> CommandError:
    # Never include source values in validation errors; they may contain private text.
    return CommandError(f"Invalid sanitized run file at {location}: {reason}")


def _public_case_id(case_id: str) -> str:
    """Map caller-provided opaque IDs to stable non-reversible report identifiers."""
    return f"case_{hashlib.sha256(case_id.encode('utf-8')).hexdigest()[:16]}"


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _load_runs(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _fail(path, "$", "file could not be read as UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise _fail(path, "$", "expected an object")
    extra_root = set(payload) - ROOT_KEYS
    missing_root = ROOT_KEYS - set(payload)
    if extra_root or missing_root:
        raise _fail(path, "$", "root keys must be exactly schema_version and runs")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise _fail(path, "schema_version", f"expected {SCHEMA_VERSION}")
    rows = payload.get("runs")
    if not isinstance(rows, list) or not rows:
        raise _fail(path, "runs", "expected a non-empty list")

    sanitized: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        at = f"runs[{index}]"
        if not isinstance(raw, dict):
            raise _fail(path, at, "expected an object")
        if set(raw) - RUN_KEYS or REQUIRED_RUN_KEYS - set(raw):
            raise _fail(path, at, "contains unknown keys or misses required keys")
        case_id = raw["case_id"]
        variant = raw["variant"]
        if not isinstance(case_id, str) or not CASE_ID_RE.fullmatch(case_id):
            raise _fail(path, f"{at}.case_id", "expected an opaque case_ identifier")
        if not isinstance(variant, str) or not VARIANT_RE.fullmatch(variant):
            raise _fail(path, f"{at}.variant", "expected baseline, agent, or candidate_<id>")
        if not _is_nonnegative_int(raw["repeat"]) or raw["repeat"] < 1:
            raise _fail(path, f"{at}.repeat", "expected a positive integer")
        for key in ("passed", "catastrophic"):
            if key in raw and not isinstance(raw[key], bool):
                raise _fail(path, f"{at}.{key}", "expected a boolean")
        if (
            "accepted" in raw
            and raw["accepted"] is not None
            and not isinstance(raw["accepted"], bool)
        ):
            raise _fail(path, f"{at}.accepted", "expected a boolean or null")
        if "duration_seconds" in raw:
            duration = raw["duration_seconds"]
            if (
                not isinstance(duration, (int, float))
                or isinstance(duration, bool)
                or not math.isfinite(duration)
                or duration < 0
            ):
                raise _fail(path, f"{at}.duration_seconds", "expected a finite nonnegative number")
        for key in ("tool_error_count", "unresolved_tool_error_count", "repair_call_count"):
            if key in raw and not _is_nonnegative_int(raw[key]):
                raise _fail(path, f"{at}.{key}", "expected a nonnegative integer")
        for key in (
            "model_call_count",
            "tool_call_count",
            "duplicate_read_count",
            "total_tokens",
            "model_duration_ms",
        ):
            if key in raw and not _is_nonnegative_int(raw[key]):
                raise _fail(path, f"{at}.{key}", "expected a nonnegative integer")
        for key in ("soft_quality", "visible_tool_count_mean"):
            if key in raw and raw[key] is not None:
                value = raw[key]
                if (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(value)
                    or value < 0
                    or key == "soft_quality"
                    and value > 1
                ):
                    raise _fail(path, f"{at}.{key}", "expected a finite nonnegative number")
        prompt_breakdown = raw.get("prompt_breakdown_tokens", {})
        if not isinstance(prompt_breakdown, dict) or any(
            not isinstance(key, str) or not _is_nonnegative_int(value)
            for key, value in prompt_breakdown.items()
        ):
            raise _fail(path, f"{at}.prompt_breakdown_tokens", "expected integer token counts")
        tool_names = raw.get("tool_names", [])
        if not isinstance(tool_names, list) or any(
            not isinstance(name, str) or not CODE_RE.fullmatch(name) for name in tool_names
        ):
            raise _fail(path, f"{at}.tool_names", "expected safe tool identifiers")
        error_categories = raw.get("error_categories", [])
        if not isinstance(error_categories, list) or any(
            not isinstance(code, str) or not CODE_RE.fullmatch(code) for code in error_categories
        ):
            raise _fail(path, f"{at}.error_categories", "expected safe error codes")
        hard_violations = raw.get("hard_violations", [])
        if not isinstance(hard_violations, list) or any(
            not isinstance(code, str) or not CODE_RE.fullmatch(code) for code in hard_violations
        ):
            raise _fail(
                path,
                f"{at}.hard_violations",
                "expected a list of lowercase violation codes",
            )

        # Copy only the allowlisted scalar values; arbitrary source fields never reach output.
        sanitized.append(
            {
                "case_id": case_id,
                "variant": variant,
                "repeat": raw["repeat"],
                "passed": raw["passed"],
                "duration_seconds": raw.get("duration_seconds"),
                "hard_violations": sorted(set(hard_violations)),
                "tool_error_count": raw.get("tool_error_count", 0),
                "unresolved_tool_error_count": raw.get("unresolved_tool_error_count", 0),
                "repair_call_count": raw.get("repair_call_count", 0),
                "accepted": raw.get("accepted"),
                "catastrophic": raw.get("catastrophic", False),
                "model_call_count": raw.get("model_call_count", 0),
                "tool_call_count": raw.get("tool_call_count", 0),
                "duplicate_read_count": raw.get("duplicate_read_count", 0),
                "total_tokens": raw.get("total_tokens", 0),
                "model_duration_ms": raw.get("model_duration_ms", 0),
                "soft_quality": raw.get("soft_quality"),
                "visible_tool_count_mean": raw.get("visible_tool_count_mean"),
                "prompt_breakdown_tokens": dict(prompt_breakdown),
                "tool_names": sorted(set(tool_names)),
                "error_categories": sorted(set(error_categories)),
            }
        )
    return sanitized


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def _distribution(values: list[float], *, higher_is_better: bool) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "p10": None,
            "worst": None,
            "variance": None,
        }
    return {
        "count": len(values),
        "mean": _round(fmean(values)),
        "median": _round(float(median(values))),
        "p10": _round(_percentile(values, 0.1)),
        "worst": _round(min(values) if higher_is_better else max(values)),
        "variance": _round(pvariance(values)),
    }


def _rate(numerator: int, denominator: int) -> float | None:
    return _round(numerator / denominator) if denominator else None


def _summarize_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    hard_counts = [float(len(row["hard_violations"])) for row in rows]
    tool_counts = [float(row["tool_error_count"]) for row in rows]
    unresolved_counts = [float(row["unresolved_tool_error_count"]) for row in rows]
    repair_counts = [float(row["repair_call_count"]) for row in rows]
    durations = [
        float(row["duration_seconds"]) for row in rows if row["duration_seconds"] is not None
    ]
    accepted = [float(row["accepted"]) for row in rows if row["accepted"] is not None]
    metrics = {
        "duration_seconds": _distribution(durations, higher_is_better=False),
        "hard_violations_per_run": _distribution(hard_counts, higher_is_better=False),
        "tool_errors_per_run": _distribution(tool_counts, higher_is_better=False),
        "unresolved_tool_errors_per_run": _distribution(unresolved_counts, higher_is_better=False),
        "repair_calls_per_run": _distribution(repair_counts, higher_is_better=False),
        "passed": _distribution([float(row["passed"]) for row in rows], higher_is_better=True),
        "accepted": _distribution(accepted, higher_is_better=True),
        "catastrophic": _distribution(
            [float(row["catastrophic"]) for row in rows], higher_is_better=False
        ),
        "model_call_count": _distribution(
            [float(row["model_call_count"]) for row in rows], higher_is_better=False
        ),
        "tool_call_count": _distribution(
            [float(row["tool_call_count"]) for row in rows], higher_is_better=False
        ),
        "duplicate_read_count": _distribution(
            [float(row["duplicate_read_count"]) for row in rows], higher_is_better=False
        ),
        "total_tokens": _distribution(
            [float(row["total_tokens"]) for row in rows], higher_is_better=False
        ),
        "model_duration_ms": _distribution(
            [float(row["model_duration_ms"]) for row in rows], higher_is_better=False
        ),
        "soft_quality": _distribution(
            [float(row["soft_quality"]) for row in rows if row["soft_quality"] is not None],
            higher_is_better=True,
        ),
        "visible_tool_count_mean": _distribution(
            [
                float(row["visible_tool_count_mean"])
                for row in rows
                if row["visible_tool_count_mean"] is not None
            ],
            higher_is_better=False,
        ),
    }
    prompt_breakdown_tokens = {
        key: sum(row["prompt_breakdown_tokens"].get(key, 0) for row in rows)
        for key in sorted({key for row in rows for key in row["prompt_breakdown_tokens"]})
    }
    tool_name_counts: dict[str, int] = {}
    error_category_counts: dict[str, int] = {}
    for row in rows:
        for name in row["tool_names"]:
            tool_name_counts[name] = tool_name_counts.get(name, 0) + 1
        for code in row["error_categories"]:
            error_category_counts[code] = error_category_counts.get(code, 0) + 1
    hard_runs = sum(bool(row["hard_violations"]) for row in rows)
    tool_error_runs = sum(row["tool_error_count"] > 0 for row in rows)
    unresolved_runs = sum(row["unresolved_tool_error_count"] > 0 for row in rows)
    repair_runs = sum(row["repair_call_count"] > 0 for row in rows)
    accepted_count = sum(bool(row["accepted"]) for row in rows if row["accepted"] is not None)
    accepted_denominator = sum(row["accepted"] is not None for row in rows)
    catastrophic_runs = sum(bool(row["catastrophic"]) for row in rows)
    passed_runs = sum(bool(row["passed"]) for row in rows)
    return {
        "run_count": count,
        "accepted_observation_count": accepted_denominator,
        "hard_violation_run_count": hard_runs,
        "tool_error_run_count": tool_error_runs,
        "tool_error_count": int(sum(row["tool_error_count"] for row in rows)),
        "unresolved_tool_error_run_count": unresolved_runs,
        "unresolved_tool_error_count": int(sum(row["unresolved_tool_error_count"] for row in rows)),
        "repair_run_count": repair_runs,
        "repair_call_count": int(sum(row["repair_call_count"] for row in rows)),
        "accepted_run_count": accepted_count,
        "catastrophic_run_count": catastrophic_runs,
        "passed_run_count": passed_runs,
        "rates": {
            "hard_violation": _rate(hard_runs, count),
            "tool_error": _rate(tool_error_runs, count),
            "unresolved_tool_error": _rate(unresolved_runs, count),
            "repair": _rate(repair_runs, count),
            "acceptance": _rate(accepted_count, accepted_denominator),
            "catastrophic": _rate(catastrophic_runs, count),
            "passed": _rate(passed_runs, count),
        },
        "metrics": metrics,
        "prompt_breakdown_tokens": prompt_breakdown_tokens,
        "tool_name_run_counts": dict(sorted(tool_name_counts.items())),
        "error_category_run_counts": dict(sorted(error_category_counts.items())),
    }


class Command(BaseCommand):
    help = "Recompute privacy-safe per-case and overall metrics from sanitized run exports."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--input",
            action="append",
            required=True,
            dest="inputs",
            help="Sanitized v1 JSON file; repeat for multiple input files.",
        )
        parser.add_argument("--output", required=True, help="Path for the sanitized summary JSON.")

    def handle(self, *args: Any, **options: Any) -> None:
        input_paths = [Path(value).expanduser().resolve() for value in options["inputs"]]
        output_path = Path(options["output"]).expanduser().resolve()
        if output_path in input_paths:
            raise CommandError("Output path must differ from every input path")

        all_rows: list[dict[str, Any]] = []
        for path in input_paths:
            all_rows.extend(_load_runs(path))
        if not all_rows:
            raise CommandError("No sanitized runs found")

        run_keys = [(row["case_id"], row["variant"], row["repeat"]) for row in all_rows]
        if len(run_keys) != len(set(run_keys)):
            raise CommandError("Duplicate (case_id, variant, repeat) rows found across inputs")

        overall = _summarize_group(all_rows)
        variants: dict[str, Any] = {}
        per_case: dict[str, Any] = {}
        for variant in sorted({row["variant"] for row in all_rows}):
            variants[variant] = _summarize_group(
                [row for row in all_rows if row["variant"] == variant]
            )
        for case_id in sorted({row["case_id"] for row in all_rows}):
            case_rows = [row for row in all_rows if row["case_id"] == case_id]
            per_case[_public_case_id(case_id)] = {
                "run_count": len(case_rows),
                "variants": {
                    variant: _summarize_group(
                        [row for row in case_rows if row["variant"] == variant]
                    )
                    for variant in sorted({row["variant"] for row in case_rows})
                },
            }

        summary = {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "source_schema_version": SCHEMA_VERSION,
            "input_file_count": len(input_paths),
            "case_count": len(per_case),
            "run_count": len(all_rows),
            "overall": overall,
            "variants": variants,
            "per_case": per_case,
            "statistical_conventions": {
                "p10": "linear interpolation at index (n - 1) * 0.10",
                "variance": "population variance",
                "worst": (
                    "maximum for durations, failures, and counts; minimum for pass/accept rates"
                ),
                "acceptance": "computed only from rows with accepted=true/false; null is excluded",
                "rate_denominators": "all runs except acceptance, which uses known observations",
            },
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote sanitized summary for {len(all_rows)} runs / {len(per_case)} cases "
                f"from {len(input_paths)} file(s): {output_path}"
            )
        )
