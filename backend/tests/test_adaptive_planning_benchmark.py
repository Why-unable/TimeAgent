import json
from typing import Any, cast

import pytest
from django.core.management import call_command

from apps.planning.adaptive_benchmark import run_adaptive_stability_benchmark


def test_adaptive_benchmark_reduces_moved_objects_without_constraint_regression() -> None:
    result = cast(dict[str, Any], run_adaptive_stability_benchmark())
    local = result["bounded_local_replan"]
    baseline = result["full_compaction_baseline"]
    assert local["moved_count"] < baseline["moved_count"]
    assert local["total_move_minutes"] < baseline["total_move_minutes"]
    assert local["deadline_violations"] == baseline["deadline_violations"] == 0
    assert local["overlap_violations"] == baseline["overlap_violations"] == 0


def test_adaptive_benchmark_command_is_reproducible(
    capsys: pytest.CaptureFixture[str],
) -> None:
    call_command("benchmark_adaptive_planning")
    first = json.loads(capsys.readouterr().out)
    call_command("benchmark_adaptive_planning")
    second = json.loads(capsys.readouterr().out)
    assert first == second
    assert first["claim"] == "synthetic_stability_comparison_not_product_outcome"
