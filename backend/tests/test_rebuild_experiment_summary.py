from __future__ import annotations

import hashlib
import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


def _write_runs(path, runs):
    path.write_text(
        json.dumps({"schema_version": "timeagent.sanitized-evaluation-runs.v1", "runs": runs}),
        encoding="utf-8",
    )


def test_rebuild_summary_aggregates_multiple_sanitized_inputs(tmp_path):
    first = tmp_path / "run-a.json"
    second = tmp_path / "run-b.json"
    output = tmp_path / "summary.json"
    _write_runs(
        first,
        [
            {
                "case_id": "case_01",
                "variant": "agent",
                "repeat": 1,
                "passed": True,
                "duration_seconds": 1,
                "hard_violations": [],
                "tool_error_count": 0,
                "repair_call_count": 0,
                "accepted": True,
                "model_call_count": 2,
                "tool_call_count": 4,
                "duplicate_read_count": 1,
                "total_tokens": 1200,
                "model_duration_ms": 2500,
                "soft_quality": 0.8,
                "visible_tool_count_mean": 8.5,
                "prompt_breakdown_tokens": {"tool_schema_tokens": 400},
                "tool_names": ["get_planning_context", "propose_schedule_plan"],
                "error_categories": [],
            },
            {
                "case_id": "case_01",
                "variant": "agent",
                "repeat": 2,
                "passed": False,
                "duration_seconds": 3,
                "hard_violations": ["deadline"],
                "tool_error_count": 2,
                "unresolved_tool_error_count": 1,
                "repair_call_count": 2,
                "accepted": False,
                "catastrophic": True,
                "model_call_count": 4,
                "tool_call_count": 6,
                "duplicate_read_count": 3,
                "total_tokens": 2200,
                "model_duration_ms": 4500,
                "soft_quality": 0.4,
                "visible_tool_count_mean": 9,
                "prompt_breakdown_tokens": {"tool_schema_tokens": 700},
                "tool_names": ["get_planning_context", "edit_schedule_plan"],
                "error_categories": ["get_planning_context"],
            },
        ],
    )
    _write_runs(
        second,
        [
            {
                "case_id": "case_01",
                "variant": "baseline",
                "repeat": 1,
                "passed": True,
                "duration_seconds": 0.5,
            }
        ],
    )

    call_command(
        "rebuild_experiment_summary",
        "--input",
        str(first),
        "--input",
        str(second),
        "--output",
        str(output),
        stdout=StringIO(),
    )

    summary = json.loads(output.read_text(encoding="utf-8"))
    agent = summary["variants"]["agent"]
    assert summary["run_count"] == 3
    assert agent["metrics"]["duration_seconds"] == {
        "count": 2,
        "mean": 2.0,
        "median": 2.0,
        "p10": 1.2,
        "worst": 3.0,
        "variance": 1.0,
    }
    assert agent["rates"]["hard_violation"] == 0.5
    assert agent["rates"]["tool_error"] == 0.5
    assert agent["rates"]["repair"] == 0.5
    assert agent["rates"]["acceptance"] == 0.5
    assert agent["rates"]["catastrophic"] == 0.5
    assert agent["metrics"]["total_tokens"]["mean"] == 1700.0
    assert agent["metrics"]["model_call_count"]["mean"] == 3.0
    assert agent["metrics"]["soft_quality"]["mean"] == 0.6
    assert agent["prompt_breakdown_tokens"] == {"tool_schema_tokens": 1100}
    assert agent["tool_name_run_counts"]["get_planning_context"] == 2
    assert agent["error_category_run_counts"] == {"get_planning_context": 1}
    expected_case_key = "case_" + hashlib.sha256(b"case_01").hexdigest()[:16]
    assert list(summary["per_case"]) == [expected_case_key]
    assert "case_01" not in output.read_text(encoding="utf-8")


def test_rebuild_summary_rejects_unallowlisted_text_without_echoing_it(tmp_path):
    source = tmp_path / "unsafe.json"
    output = tmp_path / "summary.json"
    private_text = "PRIVATE PROMPT MUST NOT LEAK"
    _write_runs(
        source,
        [
            {
                "case_id": "case_01",
                "variant": "agent",
                "repeat": 1,
                "passed": False,
                "final_response": private_text,
            }
        ],
    )

    with pytest.raises(CommandError) as error:
        call_command(
            "rebuild_experiment_summary",
            "--input",
            str(source),
            "--output",
            str(output),
            stdout=StringIO(),
        )

    assert private_text not in str(error.value)
    assert not output.exists()


def test_rebuild_summary_rejects_duplicate_repeat_rows_across_files(tmp_path):
    first = tmp_path / "run-a.json"
    second = tmp_path / "run-b.json"
    output = tmp_path / "summary.json"
    row = {"case_id": "case_01", "variant": "agent", "repeat": 1, "passed": True}
    _write_runs(first, [row])
    _write_runs(second, [row])

    with pytest.raises(CommandError, match="Duplicate"):
        call_command(
            "rebuild_experiment_summary",
            "--input",
            str(first),
            "--input",
            str(second),
            "--output",
            str(output),
            stdout=StringIO(),
        )
