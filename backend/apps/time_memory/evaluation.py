import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps.time_memory.explicit_intent import ExplicitMemoryIntent
from apps.time_memory.semantic_policy import MemoryPolicy
from apps.time_memory.semantic_schemas import MemoryProposalPayload

GOLDEN_SET_PATH = Path(__file__).parent / "fixtures" / "semantic_memory_golden.json"


@dataclass(frozen=True)
class SemanticMemoryBenchmarkReport:
    sample_count: int
    explicit_intent_accuracy: float
    enabled_policy_accuracy: float
    shadow_policy_accuracy: float
    sensitive_rejection_rate: float
    prompt_injection_rejection_rate: float
    cases: list[dict[str, object]]

    def as_dict(self) -> dict[str, object]:
        return {
            "benchmark": "semantic_memory_policy_golden",
            "sample_count": self.sample_count,
            "explicit_intent_accuracy": self.explicit_intent_accuracy,
            "enabled_policy_accuracy": self.enabled_policy_accuracy,
            "shadow_policy_accuracy": self.shadow_policy_accuracy,
            "sensitive_rejection_rate": self.sensitive_rejection_rate,
            "prompt_injection_rejection_rate": self.prompt_injection_rejection_rate,
            "cases": self.cases,
        }


def _rate(correct: int, total: int) -> float:
    return round(correct / total, 4) if total else 1.0


def _load_cases(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise ValueError("semantic memory golden set must be a JSON array of objects")
    return raw


def run_semantic_memory_benchmark(path: Path = GOLDEN_SET_PATH) -> SemanticMemoryBenchmarkReport:
    cases = _load_cases(path)
    results: list[dict[str, object]] = []
    explicit_correct = enabled_correct = shadow_correct = 0
    sensitive_total = sensitive_rejected = injection_total = injection_rejected = 0

    for case in cases:
        payload = MemoryProposalPayload(
            operation=case["operation"],
            category=case["category"],
            key=case["key"],
            value=case["value"],
            confidence=case["confidence"],
            evidence_excerpt=case["message"],
            reason_code="golden_set",
        )
        explicit = ExplicitMemoryIntent.authorizes(
            operation=payload.operation,
            user_message=case["message"],
        )
        enabled = MemoryPolicy.evaluate(
            payload,
            explicit_user_authorized=explicit,
            direct_apply_mode="enabled",
        )
        shadow = MemoryPolicy.evaluate(
            payload,
            explicit_user_authorized=explicit,
            direct_apply_mode="shadow",
        )
        expected_enabled = case["expected_enabled_action"]
        expected_shadow = case["expected_shadow_action"]
        explicit_ok = explicit == case["expected_explicit"]
        enabled_ok = enabled.action == expected_enabled
        shadow_ok = shadow.action == expected_shadow
        explicit_correct += int(explicit_ok)
        enabled_correct += int(enabled_ok)
        shadow_correct += int(shadow_ok)

        tag = case["tag"]
        if tag == "sensitive":
            sensitive_total += 1
            sensitive_rejected += int(enabled.action == "reject")
        if tag == "prompt_injection":
            injection_total += 1
            injection_rejected += int(enabled.action == "reject")
        results.append(
            {
                "id": case["id"],
                "tag": tag,
                "explicit_predicted": explicit,
                "explicit_expected": case["expected_explicit"],
                "enabled_predicted": enabled.action,
                "enabled_expected": expected_enabled,
                "shadow_predicted": shadow.action,
                "shadow_expected": expected_shadow,
                "passed": explicit_ok and enabled_ok and shadow_ok,
            }
        )

    return SemanticMemoryBenchmarkReport(
        sample_count=len(cases),
        explicit_intent_accuracy=_rate(explicit_correct, len(cases)),
        enabled_policy_accuracy=_rate(enabled_correct, len(cases)),
        shadow_policy_accuracy=_rate(shadow_correct, len(cases)),
        sensitive_rejection_rate=_rate(sensitive_rejected, sensitive_total),
        prompt_injection_rejection_rate=_rate(injection_rejected, injection_total),
        cases=results,
    )
