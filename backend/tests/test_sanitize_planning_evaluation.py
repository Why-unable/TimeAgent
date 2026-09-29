from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


def test_sanitizer_exports_only_redacted_structured_planning_outcomes(tmp_path: Path) -> None:
    source = tmp_path / "raw-evaluation.json"
    output = tmp_path / "sanitized.json"
    private_text = "PRIVATE USER TITLE AND PROMPT"
    source.write_text(
        json.dumps(
            {
                "schema_version": "timeagent.planning-harness-evaluation.v1",
                "results": [
                    {
                        "scenario_id": "synthetic-case-private-name",
                        "variant": "agent",
                        "tool_surface": "standard",
                        "repeat": 1,
                        "passed": True,
                        "duration_seconds": 2.5,
                        "model_call_count": 3,
                        "tool_call_count": 2,
                        "duplicate_read_count": 0,
                        "repair_call_count": 1,
                        "total_tokens": 1700,
                        "model_duration_ms": 1500,
                        "prompt_breakdown": {"tool_schema_tokens": 800},
                        "visible_tool_surface_stats": {
                            "mean_tool_count": 7.5,
                            "tool_names_union": ["get_planning_context", "propose_schedule_plan"],
                        },
                        "tool_error_count": 0,
                        "unresolved_tool_errors": [],
                        "catastrophic_failure": False,
                        "hard_violations": [],
                        "tool_trajectory": [
                            {
                                "name": "propose_schedule_plan",
                                "status": "success",
                                "arguments": {
                                    "task_ids": ["private-task-id"],
                                    "range_start": "2026-10-01T09:00:00+08:00",
                                    "request_text": private_text,
                                },
                                "observation": private_text,
                            }
                        ],
                        "plans": [
                            {
                                "status": "draft",
                                "task_count": 1,
                                "placed_task_count": 1,
                                "unplaced_task_keys": [],
                                "placed_minutes": 60,
                                "placed_segments": 1,
                                "distinct_days": ["2026-10-01"],
                                "distinct_weeks": ["2026-W40"],
                                "schedule": {
                                    private_text: [
                                        {
                                            "start_at": "2026-10-01T09:00:00+08:00",
                                            "end_at": "2026-10-01T10:00:00+08:00",
                                        }
                                    ]
                                },
                                "hard_violations": ["deadline:private-task-id"],
                                "soft_check_pass_rate": 0.75,
                                "soft_checks": [
                                    {"name": "preferred_unplaced:private-task-id", "passed": True}
                                ],
                            }
                        ],
                        "final_response": private_text,
                        "task_facts": [{"title": private_text}],
                    },
                    {
                        "scenario_id": "synthetic-provider-error",
                        "variant": "agent",
                        "tool_surface": "standard",
                        "repeat": 1,
                        "passed": False,
                        "error_type": "PermissionDeniedError",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    call_command("sanitize_planning_evaluation", "--input", str(source), "--output", str(output))

    exported_text = output.read_text(encoding="utf-8")
    artifact = json.loads(exported_text)
    row = artifact["runs"][0]
    assert artifact["schema_version"] == "timeagent.sanitized-evaluation-runs.v1"
    assert (
        row["case_id"] == "case_" + hashlib.sha256(b"synthetic-case-private-name").hexdigest()[:16]
    )
    assert row["variant"] == "candidate_standard"
    assert row["tool_calls"][0]["arguments_redacted"] == {
        "task_ids": ["[redacted:string]"],
        "range_start": "[redacted:datetime]",
        "request_text": "[redacted:string]",
    }
    assert row["final_schedule"][0]["schedule"] == [
        {
            "task_id": "task_01",
            "segments": [
                {
                    "start_at": "2026-10-01T09:00:00+08:00",
                    "end_at": "2026-10-01T10:00:00+08:00",
                }
            ],
        }
    ]
    assert row["hard_violations"] == ["deadline"]
    assert artifact["runs"][1]["error_categories"] == ["permissiondeniederror"]
    assert private_text not in exported_text
    assert "private-task-id" not in exported_text
    assert "synthetic-case-private-name" not in exported_text


def test_sanitizer_rejects_non_evaluation_input_without_echoing_contents(tmp_path: Path) -> None:
    source = tmp_path / "unsafe.json"
    output = tmp_path / "sanitized.json"
    private_text = "DO NOT ECHO THIS PROMPT"
    source.write_text(json.dumps({"raw_prompt": private_text}), encoding="utf-8")

    with pytest.raises(CommandError) as error:
        call_command(
            "sanitize_planning_evaluation", "--input", str(source), "--output", str(output)
        )

    assert private_text not in str(error.value)
    assert not output.exists()
