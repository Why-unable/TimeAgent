import json

from apps.time_memory.evaluation import run_semantic_memory_benchmark


def test_semantic_memory_golden_set_is_reproducible_and_passes() -> None:
    report = run_semantic_memory_benchmark()

    assert report.sample_count == 12
    assert report.explicit_intent_accuracy == 1.0
    assert report.enabled_policy_accuracy == 1.0
    assert report.shadow_policy_accuracy == 1.0
    assert report.sensitive_rejection_rate == 1.0
    assert report.prompt_injection_rejection_rate == 1.0
    assert all(case["passed"] is True for case in report.cases)
    assert json.loads(json.dumps(report.as_dict(), ensure_ascii=False))["sample_count"] == 12
