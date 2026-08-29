import json
from typing import Any, cast

import pytest
from django.core.management import call_command

from apps.planning.benchmark import run_default_benchmark


def test_default_planning_benchmark_is_deterministic() -> None:
    first = cast(dict[str, Any], run_default_benchmark())
    second = cast(dict[str, Any], run_default_benchmark())

    assert first == second
    assert first["benchmark"] == "planning-baseline-v1"
    assert first["algorithm"] == "first-fit-in-input-order"
    assert first["case_count"] == 4
    assert first["task_count"] == 11
    assert first["comparison"]["algorithm"] == "longest-first-best-fit-candidate"
    assert first["comparison"]["scheduled_count"] > first["scheduled_count"]
    assert first["comparison"]["hard_constraint_violations"] == 0
    assert all(case["hard_constraint_violations"] == 0 for case in first["cases"])


def test_planning_benchmark_management_command_emits_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    call_command("benchmark_planning")

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)
    assert payload["benchmark"] == "planning-baseline-v1"
    assert payload["scheduled_count"] == 7
