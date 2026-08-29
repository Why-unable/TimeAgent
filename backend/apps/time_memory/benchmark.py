from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from django.contrib.auth.models import User

from apps.tasks.models import Task
from apps.time_memory.decision_profile import calibrated_confidence, time_decayed_ratio
from apps.time_memory.duration_evidence import DurationEvidence, duration_evidence_for_tasks


@dataclass(frozen=True, slots=True)
class DurationBenchmarkResult:
    sample_count: int
    train_count: int
    test_count: int
    baseline_fixed_30_mae: float | None
    baseline_user_estimate_mae: float | None
    calibrated_mae: float | None
    stratified_mae: float | None
    confidence_calibration_error: float | None
    calibration_bins: tuple[dict[str, object], ...]
    segment_count: int
    semantic_segment_count: int
    stratified_fallback_count: int
    train_ratio: float | None
    status: str

    def as_dict(self) -> dict[str, object]:
        return {
            "sample_count": self.sample_count,
            "train_count": self.train_count,
            "test_count": self.test_count,
            "baseline_fixed_30_mae": self.baseline_fixed_30_mae,
            "baseline_user_estimate_mae": self.baseline_user_estimate_mae,
            "calibrated_mae": self.calibrated_mae,
            "stratified_mae": self.stratified_mae,
            "confidence_calibration_error": self.confidence_calibration_error,
            "calibration_bins": list(self.calibration_bins),
            "segment_count": self.segment_count,
            "semantic_segment_count": self.semantic_segment_count,
            "stratified_fallback_count": self.stratified_fallback_count,
            "train_ratio": self.train_ratio,
            "status": self.status,
        }


def benchmark_duration_profile(*, user: User, min_samples: int = 10) -> DurationBenchmarkResult:
    tasks = list(
        Task.objects.filter(user=user, estimated_minutes__isnull=False).order_by(
            "completed_at", "id"
        )
    )
    rows = duration_evidence_for_tasks(tasks)
    if len(rows) < min_samples:
        return DurationBenchmarkResult(
            sample_count=len(rows),
            train_count=0,
            test_count=0,
            baseline_fixed_30_mae=None,
            baseline_user_estimate_mae=None,
            calibrated_mae=None,
            stratified_mae=None,
            confidence_calibration_error=None,
            calibration_bins=(),
            segment_count=0,
            semantic_segment_count=0,
            stratified_fallback_count=0,
            train_ratio=None,
            status="insufficient_data",
        )
    split = max(1, int(len(rows) * 0.7))
    if split >= len(rows):
        split = len(rows) - 1
    train = rows[:split]
    test = rows[split:]
    prediction_anchor = test[0].observed_at
    ratio = time_decayed_ratio(train, now=prediction_anchor)
    segment_rows: dict[str, list[DurationEvidence]] = {}
    semantic_rows: dict[str, list[DurationEvidence]] = {}
    for row in train:
        segment_rows.setdefault(row.segment, []).append(row)
        semantic_rows.setdefault(row.semantic_segment, []).append(row)
    segment_ratios = {
        segment: time_decayed_ratio(segment_train, now=prediction_anchor)
        for segment, segment_train in segment_rows.items()
        if segment != "uncategorized" and len(segment_train) >= 3
    }
    semantic_ratios = {
        segment: time_decayed_ratio(segment_train, now=prediction_anchor)
        for segment, segment_train in semantic_rows.items()
        if segment != "semantic:unclassified" and len(segment_train) >= 3
    }
    predictions: list[tuple[DurationEvidence, float, float]] = []
    for row in test:
        selected_rows = train
        selected_ratio = ratio
        if row.segment in segment_ratios:
            selected_rows = segment_rows[row.segment]
            selected_ratio = segment_ratios[row.segment]
        elif row.semantic_segment in semantic_ratios:
            selected_rows = semantic_rows[row.semantic_segment]
            selected_ratio = semantic_ratios[row.semantic_segment]
        predictions.append(
            (
                row,
                row.estimated_minutes * selected_ratio,
                calibrated_confidence(
                    selected_rows,
                    multiplier=selected_ratio,
                    now=row.observed_at,
                ),
            )
        )
    return DurationBenchmarkResult(
        sample_count=len(rows),
        train_count=len(train),
        test_count=len(test),
        baseline_fixed_30_mae=round(_mae(test, lambda row: 30.0), 3),
        baseline_user_estimate_mae=round(_mae(test, lambda row: row.estimated_minutes), 3),
        calibrated_mae=round(_mae(test, lambda row: row.estimated_minutes * ratio), 3),
        stratified_mae=round(
            sum(abs(predicted - row.actual_minutes) for row, predicted, _ in predictions)
            / len(predictions),
            3,
        ),
        confidence_calibration_error=round(
            sum(
                abs(
                    confidence
                    - float(abs(predicted - row.actual_minutes) / row.actual_minutes <= 0.25)
                )
                for row, predicted, confidence in predictions
            )
            / len(predictions),
            3,
        ),
        calibration_bins=_calibration_bins(predictions),
        segment_count=len(segment_ratios),
        semantic_segment_count=len(semantic_ratios),
        stratified_fallback_count=sum(
            1
            for row in test
            if row.segment not in segment_ratios and row.semantic_segment not in semantic_ratios
        ),
        train_ratio=round(ratio, 3),
        status="ok",
    )


def _mae(rows: list[DurationEvidence], predictor: Callable[[DurationEvidence], float]) -> float:
    return sum(abs(predictor(row) - row.actual_minutes) for row in rows) / len(rows)


def _calibration_bins(
    predictions: list[tuple[DurationEvidence, float, float]],
) -> tuple[dict[str, object], ...]:
    bins: list[dict[str, object]] = []
    for lower, upper in ((0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.0)):
        selected = [
            (row, predicted, confidence)
            for row, predicted, confidence in predictions
            if lower <= confidence < upper or (upper == 1.0 and confidence == 1.0)
        ]
        if not selected:
            continue
        observed = [
            float(abs(predicted - row.actual_minutes) / row.actual_minutes <= 0.25)
            for row, predicted, _ in selected
        ]
        bins.append(
            {
                "lower": lower,
                "upper": upper,
                "sample_count": len(selected),
                "mean_confidence": round(
                    sum(confidence for _, _, confidence in selected) / len(selected),
                    3,
                ),
                "observed_accuracy": round(sum(observed) / len(observed), 3),
            }
        )
    return tuple(bins)
