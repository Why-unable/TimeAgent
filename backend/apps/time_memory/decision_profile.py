from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from langgraph.store.base import BaseStore

from apps.preferences.models import UserPreference
from apps.tasks.models import Task
from apps.time_memory.duration_evidence import (
    DurationEvidence,
    duration_evidence_for_tasks,
    explicit_task_segment,
)
from apps.time_memory.models import (
    TimeDecisionFeedback,
    TimeDecisionFeedbackAction,
)
from apps.time_memory.repository import TimeMemoryRepository
from apps.time_memory.schemas import TimeMemoryProfile
from apps.time_memory.task_classification import TaskClassification, classify_task
from common.time import to_utc

DURATION_CATEGORY = "duration_estimate"
DURATION_RECOMMENDATION_VERSION = "duration-recommendation-v2"
DURATION_RECOMMENDATION_TTL = timedelta(days=7)
DURATION_DECAY_HALF_LIFE_DAYS = 60


@dataclass(frozen=True, slots=True)
class DecisionProfile:
    version: int
    generated_at: str | None
    category: str
    enabled: bool
    default_duration_minutes: int
    duration_multiplier: float
    confidence: float
    sample_count: int
    source: str
    evidence: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "category": self.category,
            "enabled": self.enabled,
            "default_duration_minutes": self.default_duration_minutes,
            "duration_multiplier": self.duration_multiplier,
            "confidence": self.confidence,
            "sample_count": self.sample_count,
            "source": self.source,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class DurationRecommendation:
    task_id: str
    original_estimate_minutes: int | None
    recommended_minutes: int
    duration_multiplier: float
    segment: str
    confidence: float
    sample_count: int
    source: str
    fallback_reason: str | None
    evidence: tuple[str, ...]
    classification: TaskClassification
    feature_version: str
    expires_at: str
    decay_half_life_days: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "original_estimate_minutes": self.original_estimate_minutes,
            "recommended_minutes": self.recommended_minutes,
            "duration_multiplier": self.duration_multiplier,
            "segment": self.segment,
            "confidence": self.confidence,
            "sample_count": self.sample_count,
            "source": self.source,
            "fallback_reason": self.fallback_reason,
            "evidence": list(self.evidence),
            "classification": self.classification.as_dict(),
            "feature_version": self.feature_version,
            "expires_at": self.expires_at,
            "decay_half_life_days": self.decay_half_life_days,
        }


@dataclass(frozen=True, slots=True)
class RecordDecisionFeedbackCommand:
    user: User
    category: str
    action: TimeDecisionFeedbackAction | str
    value: dict[str, Any]
    idempotency_key: str
    source: str = "web"


class DecisionProfileService:
    """Build a small, explainable profile consumed by future planning features."""

    @staticmethod
    def get(*, user: User, store: BaseStore) -> DecisionProfile:
        preference, _ = UserPreference.objects.get_or_create(user=user)
        profile = TimeMemoryRepository.get(store, user_id=str(user.pk))
        feedback = next(
            (
                item
                for item in TimeDecisionFeedback.objects.filter(
                    user=user,
                    category=DURATION_CATEGORY,
                    action__in=[
                        TimeDecisionFeedbackAction.DISABLE,
                        TimeDecisionFeedbackAction.OVERRIDE,
                    ],
                ).order_by("-created_at", "-id")[:100]
                if item.action == TimeDecisionFeedbackAction.OVERRIDE
                or not item.value.get("segment")
            ),
            None,
        )
        return DecisionProfileService._build(
            preference=preference,
            profile=profile,
            feedback=feedback,
        )

    @staticmethod
    @transaction.atomic
    def record_feedback(command: RecordDecisionFeedbackCommand) -> TimeDecisionFeedback:
        if command.user.pk is None:
            raise ValueError("Decision feedback user must be persisted")
        category = command.category.strip()
        source = command.source.strip()
        key = command.idempotency_key.strip()
        if not category or not source or not key:
            raise ValueError("category, source and idempotency_key are required")
        action = TimeDecisionFeedbackAction(command.action)
        if not isinstance(command.value, dict):
            raise ValueError("value must be an object")
        if action in {
            TimeDecisionFeedbackAction.TOO_SHORT,
            TimeDecisionFeedbackAction.TOO_LONG,
        }:
            segment = command.value.get("segment")
            if not isinstance(segment, str) or not segment.strip():
                raise ValueError("Task duration feedback requires an explicit segment")
        existing = (
            TimeDecisionFeedback.objects.select_for_update()
            .filter(
                user=command.user,
                idempotency_key=key,
            )
            .first()
        )
        if existing is not None:
            if (
                existing.category != category
                or existing.action != action
                or existing.value != command.value
                or existing.source != source
            ):
                raise ValueError("Idempotency key was already used for different feedback")
            return existing
        feedback = TimeDecisionFeedback(
            user=command.user,
            category=category,
            action=action,
            value=command.value,
            idempotency_key=key,
            source=source,
        )
        feedback.full_clean()
        feedback.save(force_insert=True)
        return feedback

    @staticmethod
    def recommend_duration(
        *,
        user: User,
        store: BaseStore,
        task_id: UUID,
        now: datetime | None = None,
        min_segment_samples: int = 3,
    ) -> DurationRecommendation:
        task = Task.objects.get(pk=task_id, user=user)
        base = DecisionProfileService.get(user=user, store=store)
        original = task.estimated_minutes
        baseline = original or base.default_duration_minutes
        classification = classify_task(task)
        explicit_segment = explicit_task_segment(task)
        current = to_utc(now or timezone.now())
        expires_at = (current + DURATION_RECOMMENDATION_TTL).isoformat()
        if not base.enabled:
            return DurationRecommendation(
                task_id=str(task.pk),
                original_estimate_minutes=original,
                recommended_minutes=baseline,
                duration_multiplier=1.0,
                segment=explicit_segment,
                confidence=0.0,
                sample_count=0,
                source="user_disabled",
                fallback_reason="duration_learning_disabled",
                evidence=("用户已关闭估时学习建议",),
                classification=classification,
                feature_version=DURATION_RECOMMENDATION_VERSION,
                expires_at=expires_at,
                decay_half_life_days=DURATION_DECAY_HALF_LIFE_DAYS,
            )

        historical = list(
            Task.objects.filter(
                user=user,
                completed_at__gte=current - timedelta(days=180),
                completed_at__lt=current,
                estimated_minutes__isnull=False,
            ).exclude(pk=task.pk)
        )
        rows = duration_evidence_for_tasks(historical)
        explicit_rows = [row for row in rows if row.segment == explicit_segment]
        semantic_rows = [row for row in rows if row.semantic_segment == classification.segment]
        selected_rows: list[DurationEvidence] = []
        segment = explicit_segment
        evidence: tuple[str, ...]
        if explicit_segment != "uncategorized" and len(explicit_rows) >= min_segment_samples:
            selected_rows = explicit_rows
            source = "explicit_segment_execution_calibration"
            fallback_reason = None
        elif (
            classification.category != "unclassified" and len(semantic_rows) >= min_segment_samples
        ):
            selected_rows = semantic_rows
            segment = classification.segment
            source = "semantic_similarity_execution_calibration"
            fallback_reason = (
                "explicit_segment_sample_below_minimum"
                if explicit_segment != "uncategorized"
                else None
            )
        if selected_rows:
            multiplier = time_decayed_ratio(selected_rows, now=current)
            confidence = calibrated_confidence(
                selected_rows,
                multiplier=multiplier,
                now=current,
            )
            sample_count = len(selected_rows)
            evidence = (
                f"最近 180 天同类的 {sample_count} 个完成任务",
                f"分组依据 {segment}",
                (
                    f"按 {DURATION_DECAY_HALF_LIFE_DAYS} 天半衰期加权的"
                    f"实际/预计时长比 {multiplier:.2f}"
                ),
            )
        else:
            multiplier = base.duration_multiplier
            confidence = base.confidence
            source = base.source
            sample_count = base.sample_count
            fallback_reason = "segment_sample_below_minimum"
            evidence = (
                (
                    f"明确分组仅有 {len(explicit_rows)} 个样本，"
                    f"语义同类仅有 {len(semantic_rows)} 个样本，"
                    f"门槛为 {min_segment_samples}"
                ),
                *base.evidence,
            )
        segment_disabled = next(
            (
                item
                for item in TimeDecisionFeedback.objects.filter(
                    user=user,
                    category=DURATION_CATEGORY,
                    action=TimeDecisionFeedbackAction.DISABLE,
                ).order_by("-created_at", "-id")[:100]
                if item.value.get("segment") == segment
            ),
            None,
        )
        if segment_disabled is not None:
            return DurationRecommendation(
                task_id=str(task.pk),
                original_estimate_minutes=original,
                recommended_minutes=baseline,
                duration_multiplier=1.0,
                segment=segment,
                confidence=0.0,
                sample_count=0,
                source="user_disabled_segment",
                fallback_reason="duration_segment_disabled",
                evidence=(f"用户已关闭 {segment} 的估时建议",),
                classification=classification,
                feature_version=DURATION_RECOMMENDATION_VERSION,
                expires_at=expires_at,
                decay_half_life_days=DURATION_DECAY_HALF_LIFE_DAYS,
            )
        task_feedback = next(
            (
                item
                for item in TimeDecisionFeedback.objects.filter(
                    user=user,
                    category=DURATION_CATEGORY,
                    action__in=[
                        TimeDecisionFeedbackAction.ACCEPT,
                        TimeDecisionFeedbackAction.TOO_SHORT,
                        TimeDecisionFeedbackAction.TOO_LONG,
                    ],
                ).order_by("-created_at", "-id")[:100]
                if item.value.get("segment") == segment
            ),
            None,
        )
        if task_feedback is not None:
            if task_feedback.action == TimeDecisionFeedbackAction.TOO_SHORT:
                multiplier = min(4.0, multiplier * 1.25)
                confidence = max(confidence, 0.5)
                source = "user_segment_feedback"
                evidence = (*evidence, "用户反馈同类任务建议偏短，倍率上调 25%")
            elif task_feedback.action == TimeDecisionFeedbackAction.TOO_LONG:
                multiplier = max(0.25, multiplier * 0.8)
                confidence = max(confidence, 0.5)
                source = "user_segment_feedback"
                evidence = (*evidence, "用户反馈同类任务建议偏长，倍率下调 20%")
            else:
                evidence = (*evidence, "用户确认同类任务的当前估时建议")
        return DurationRecommendation(
            task_id=str(task.pk),
            original_estimate_minutes=original,
            recommended_minutes=max(1, round(baseline * multiplier)),
            duration_multiplier=round(multiplier, 3),
            segment=segment,
            confidence=round(confidence, 3),
            sample_count=sample_count,
            source=source,
            fallback_reason=fallback_reason,
            evidence=evidence,
            classification=classification,
            feature_version=DURATION_RECOMMENDATION_VERSION,
            expires_at=expires_at,
            decay_half_life_days=DURATION_DECAY_HALF_LIFE_DAYS,
        )

    @staticmethod
    def _build(
        *,
        preference: UserPreference,
        profile: TimeMemoryProfile | None,
        feedback: TimeDecisionFeedback | None,
    ) -> DecisionProfile:
        default_minutes = 30
        multiplier = 1.0
        confidence = 0.0
        sample_count = 0
        source = "global_default"
        evidence: list[str] = ["固定 30 分钟冷启动 baseline"]
        generated_at = None
        version = 1
        if profile is not None:
            generated_at = profile.generated_at.isoformat()
            version = profile.version
            calibration = profile.behavior_windows.get("30d")
            if calibration is not None and calibration.execution_calibration.sample_count:
                execution = calibration.execution_calibration
                multiplier = max(0.25, min(4.0, execution.median_actual_to_estimated_ratio))
                confidence = execution.confidence
                sample_count = execution.sample_count
                source = "execution_calibration"
                evidence = [
                    f"最近 30 天 {sample_count} 个完成任务的执行证据",
                    f"实际/预计时长中位比 {multiplier:.2f}",
                ]
        enabled = preference.time_memory_enabled and preference.time_memory_allow_context_injection
        if feedback is not None:
            if feedback.action == TimeDecisionFeedbackAction.DISABLE:
                enabled = False
                source = "user_disabled"
                evidence = ["用户关闭 duration_estimate 建议"]
            elif feedback.action == TimeDecisionFeedbackAction.OVERRIDE:
                override = feedback.value.get("duration_multiplier")
                if isinstance(override, (int, float)) and not isinstance(override, bool):
                    multiplier = max(0.25, min(4.0, float(override)))
                    confidence = 1.0
                    source = "user_override"
                    evidence = ["用户覆盖 duration_estimate 建议"]
        return DecisionProfile(
            version=version,
            generated_at=generated_at,
            category=DURATION_CATEGORY,
            enabled=enabled,
            default_duration_minutes=default_minutes,
            duration_multiplier=round(multiplier, 3),
            confidence=round(confidence, 3),
            sample_count=sample_count,
            source=source,
            evidence=tuple(evidence),
        )


def time_decayed_ratio(rows: list[DurationEvidence], *, now: datetime) -> float:
    weighted = sorted(
        (
            row.actual_minutes / row.estimated_minutes,
            recency_weight(row.observed_at, now=now),
        )
        for row in rows
    )
    total_weight = sum(weight for _, weight in weighted)
    threshold = total_weight / 2
    cumulative = 0.0
    ratio = 1.0
    for value, weight in weighted:
        cumulative += weight
        ratio = value
        if cumulative >= threshold:
            break
    return float(max(0.25, min(4.0, ratio)))


def calibrated_confidence(
    rows: list[DurationEvidence],
    *,
    multiplier: float,
    now: datetime,
) -> float:
    weights = [recency_weight(row.observed_at, now=now) for row in rows]
    total_weight = sum(weights)
    successful_weight = sum(
        weight
        for row, weight in zip(rows, weights, strict=True)
        if abs(row.estimated_minutes * multiplier - row.actual_minutes) / row.actual_minutes <= 0.25
    )
    empirical_probability = (successful_weight + 1.0) / (total_weight + 2.0)
    sample_strength = min(1.0, total_weight / 5.0)
    return round(empirical_probability * sample_strength, 3)


def recency_weight(observed_at: datetime, *, now: datetime) -> float:
    age_days = max(0.0, (to_utc(now) - to_utc(observed_at)).total_seconds() / 86400)
    return float(0.5 ** (age_days / DURATION_DECAY_HALF_LIFE_DAYS))
