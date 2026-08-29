from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from apps.insights.attention import AttentionPolicy
from apps.insights.models import TemporalInsight, TemporalInsightStatus
from apps.notifications.models import NotificationDelivery, NotificationSourceType
from apps.notifications.services import CreateDeliveryCommand, NotificationService
from apps.preferences.services import UserPreferenceService
from apps.tasks.models import Task, TaskStatus
from apps.time_memory.capacity import CapacityForecastService
from common.time import to_utc


@dataclass(frozen=True, slots=True)
class InsightScanResult:
    created_count: int
    updated_count: int
    expired_count: int


class TemporalInsightService:
    """Deterministic detector and attention-state boundary for proactive insights."""

    @staticmethod
    @transaction.atomic
    def scan(*, user: User, now: datetime | None = None) -> InsightScanResult:
        current = to_utc(now or timezone.now())
        expired_count = TemporalInsight.objects.filter(
            user=user,
            status__in=[TemporalInsightStatus.OPEN, TemporalInsightStatus.SNOOZED],
            expires_at__lte=current,
        ).update(status=TemporalInsightStatus.EXPIRED, updated_at=current)
        created = updated = 0
        horizon = current + timedelta(hours=48)
        tasks = Task.objects.filter(
            user=user,
            status__in=[TaskStatus.PENDING, TaskStatus.IN_PROGRESS],
            due_at__isnull=False,
            due_at__lte=horizon,
        ).order_by("due_at", "id")
        for task in tasks:
            if task.due_at is None:
                continue
            due_at = to_utc(task.due_at)
            overdue = due_at <= current
            kind = "overdue_task" if overdue else "deadline_risk"
            severity = "high" if overdue else "medium"
            deduplication_key = f"{kind}:{task.pk}:{due_at.date().isoformat()}"
            title = "任务已经逾期" if overdue else "任务截止时间临近"
            remaining_hours = max(0, int((due_at - current).total_seconds() // 3600))
            summary = (
                f"“{task.title}”已超过截止时间。"
                if overdue
                else f"“{task.title}”将在 {remaining_hours} 小时内截止，当前尚未完成。"
            )
            expires_at = max(due_at + timedelta(days=1), current + timedelta(hours=24))
            candidate = TemporalInsight(
                user=user,
                kind=kind,
                severity=severity,
                title=title,
                summary=summary,
                evidence={
                    "task_id": str(task.pk),
                    "task_version": task.version,
                    "due_at": due_at.isoformat(),
                    "priority": task.priority,
                    "estimated_minutes": task.estimated_minutes,
                },
                deduplication_key=deduplication_key,
                detected_at=current,
                expires_at=expires_at,
            )
            attention = AttentionPolicy.decide(user=user, insight=candidate, now=current)
            defaults = {
                "kind": kind,
                "severity": severity,
                "title": title,
                "summary": summary,
                "evidence": candidate.evidence,
                "detected_at": current,
                "expires_at": expires_at,
                "attention_decision": attention.decision,
                "attention_reason": attention.reason,
                "attention_decided_at": current,
            }
            insight, was_created = TemporalInsight.objects.get_or_create(
                user=user,
                deduplication_key=deduplication_key,
                defaults=defaults,
            )
            if not was_created:
                TemporalInsightService._refresh_existing(
                    insight=insight,
                    defaults=defaults,
                    current=current,
                )
            if was_created:
                created += 1
            else:
                updated += 1
        forecast = CapacityForecastService.forecast(
            user=user,
            range_start=current,
            range_end=horizon,
        )
        if forecast.risk in {"over_capacity", "tight"}:
            kind = "capacity_risk"
            deduplication_key = f"{kind}:{current.date().isoformat()}"
            severity = "high" if forecast.risk == "over_capacity" else "medium"
            candidate = TemporalInsight(
                user=user,
                kind=kind,
                severity=severity,
                title="未来两天容量紧张",
                summary=(
                    f"未来两天预计有 {forecast.unplanned_minutes} 分钟未安排工作，"
                    f"可用空闲约 {forecast.available_minutes} 分钟。"
                ),
                evidence={
                    "range_start": forecast.range_start.isoformat(),
                    "range_end": forecast.range_end.isoformat(),
                    "available_minutes": forecast.available_minutes,
                    "committed_minutes": forecast.committed_minutes,
                    "unplanned_minutes": forecast.unplanned_minutes,
                    "reason_codes": list(forecast.reason_codes),
                },
                deduplication_key=deduplication_key,
                detected_at=current,
                expires_at=horizon,
            )
            attention = AttentionPolicy.decide(user=user, insight=candidate, now=current)
            defaults = {
                "kind": candidate.kind,
                "severity": candidate.severity,
                "title": candidate.title,
                "summary": candidate.summary,
                "evidence": candidate.evidence,
                "detected_at": current,
                "expires_at": horizon,
                "attention_decision": attention.decision,
                "attention_reason": attention.reason,
                "attention_decided_at": current,
            }
            insight, was_created = TemporalInsight.objects.get_or_create(
                user=user, deduplication_key=deduplication_key, defaults=defaults
            )
            if not was_created:
                TemporalInsightService._refresh_existing(
                    insight=insight,
                    defaults=defaults,
                    current=current,
                )
                updated += 1
            else:
                created += 1
        return InsightScanResult(
            created_count=created, updated_count=updated, expired_count=expired_count
        )

    @staticmethod
    def list_open(*, user: User, now: datetime | None = None) -> list[TemporalInsight]:
        current = to_utc(now or timezone.now())
        preference = UserPreferenceService.get_or_create_for_user(user)
        TemporalInsight.objects.filter(
            user=user,
            status__in=[TemporalInsightStatus.OPEN, TemporalInsightStatus.SNOOZED],
            expires_at__lte=current,
        ).update(status=TemporalInsightStatus.EXPIRED, updated_at=current)
        return list(
            TemporalInsight.objects.filter(user=user, status=TemporalInsightStatus.OPEN)
            .exclude(kind__in=preference.disabled_insight_kinds)
            .order_by("-severity", "expires_at", "-detected_at")
        )

    @staticmethod
    def get(*, user: User, insight_id: UUID) -> TemporalInsight:
        return TemporalInsight.objects.get(pk=insight_id, user=user)

    @staticmethod
    @transaction.atomic
    def materialize_notifications(*, user: User, now: datetime | None = None) -> int:
        """Create idempotent delivery facts for already-approved insight decisions."""
        current = to_utc(now or timezone.now())
        insights = TemporalInsight.objects.filter(
            user=user,
            status=TemporalInsightStatus.OPEN,
            expires_at__gt=current,
            attention_decision__in=["NORMAL_NOTIFICATION", "HIGH_PRIORITY_NOTIFICATION"],
        ).order_by("detected_at", "id")
        preference = UserPreferenceService.get_or_create_for_user(user)
        if preference.disabled_insight_kinds:
            insights = insights.exclude(kind__in=preference.disabled_insight_kinds)
        channels = NotificationService.channels_for(
            user=user, source_type=NotificationSourceType.SYSTEM
        )
        created = 0
        for insight in insights:
            for channel in channels:
                deduplication_key = f"insight:v2:{insight.pk}:{channel}"
                existing_source_delivery = NotificationDelivery.objects.filter(
                    user=user,
                    source_type=NotificationSourceType.SYSTEM,
                    source_id=insight.pk,
                    channel_type=channel,
                ).first()
                if existing_source_delivery is not None:
                    # Delivery facts are immutable after materialization. Later scans may
                    # refresh the insight summary, but cannot rewrite or duplicate a send.
                    continue
                NotificationService.create_delivery(
                    CreateDeliveryCommand(
                        user=user,
                        source_type=NotificationSourceType.SYSTEM,
                        source_id=insight.pk,
                        channel_type=channel,
                        deduplication_key=deduplication_key,
                        subject=insight.title,
                        body=insight.summary,
                        scheduled_at=insight.attention_decided_at or insight.detected_at,
                        payload={
                            "url": f"/insights/{insight.pk}",
                            "insight_id": str(insight.pk),
                            "insight_kind": insight.kind,
                            "attention_decision": insight.attention_decision,
                            "attention_reason": insight.attention_reason,
                        },
                    )
                )
                created += 1
        return created

    @staticmethod
    def _refresh_existing(
        *,
        insight: TemporalInsight,
        defaults: dict[str, object],
        current: datetime,
    ) -> None:
        decision_changed = (
            insight.attention_decision != defaults["attention_decision"]
            or insight.attention_reason != defaults["attention_reason"]
        )
        update_fields: list[str] = []
        for field, value in defaults.items():
            if field in {"detected_at", "attention_decided_at"}:
                continue
            setattr(insight, field, value)
            update_fields.append(field)
        if decision_changed:
            insight.attention_decided_at = current
            update_fields.append("attention_decided_at")
        insight.save(update_fields=[*update_fields, "updated_at"])

    @staticmethod
    @transaction.atomic
    def act(
        *,
        user: User,
        insight_id: UUID,
        action: str,
        until: datetime | None = None,
        disable_kind: bool = False,
    ) -> TemporalInsight:
        insight = TemporalInsight.objects.select_for_update().get(pk=insight_id, user=user)
        if insight.status in {
            TemporalInsightStatus.DISMISSED,
            TemporalInsightStatus.ACTIONED,
            TemporalInsightStatus.EXPIRED,
            TemporalInsightStatus.FALSE_POSITIVE,
        }:
            if insight.status == TemporalInsightStatus.FALSE_POSITIVE and disable_kind:
                TemporalInsightService._disable_kind(user=user, insight=insight)
            return insight
        acted_at = timezone.now()
        if action == "snooze":
            snoozed_until = (
                to_utc(until) if until is not None else timezone.now() + timedelta(hours=4)
            )
            if snoozed_until >= insight.expires_at:
                insight.status = TemporalInsightStatus.EXPIRED
            else:
                insight.status = TemporalInsightStatus.SNOOZED
                insight.snoozed_until = snoozed_until
        elif action == "dismiss":
            insight.status = TemporalInsightStatus.DISMISSED
            insight.acted_at = acted_at
        elif action == "actioned":
            insight.status = TemporalInsightStatus.ACTIONED
            insight.acted_at = acted_at
        elif action == "false_positive":
            insight.status = TemporalInsightStatus.FALSE_POSITIVE
            insight.acted_at = acted_at
            if disable_kind:
                TemporalInsightService._disable_kind(user=user, insight=insight)
        else:
            raise ValueError("Unsupported insight action")
        insight.save(update_fields=["status", "snoozed_until", "acted_at", "updated_at"])
        if action in {"dismiss", "actioned", "false_positive"}:
            NotificationService.cancel_source_deliveries(
                user=user,
                source_type=NotificationSourceType.SYSTEM,
                source_ids=[insight.pk],
                occurred_at=acted_at,
            )
        return insight

    @staticmethod
    def _disable_kind(*, user: User, insight: TemporalInsight) -> None:
        preference = UserPreferenceService.get_or_create_for_user(user)
        disabled_kinds = sorted({*preference.disabled_insight_kinds, insight.kind})
        if disabled_kinds != preference.disabled_insight_kinds:
            UserPreferenceService.update_for_user(user, {"disabled_insight_kinds": disabled_kinds})
        source_ids = list(
            TemporalInsight.objects.filter(user=user, kind=insight.kind).values_list(
                "id", flat=True
            )
        )
        NotificationService.cancel_source_deliveries(
            user=user,
            source_type=NotificationSourceType.SYSTEM,
            source_ids=source_ids,
            occurred_at=timezone.now(),
        )
