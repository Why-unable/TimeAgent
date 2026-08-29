from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.contrib.auth.models import User

from apps.insights.models import TemporalInsight, TemporalInsightStatus
from apps.notifications.models import (
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationSourceType,
)
from apps.preferences.models import UserPreference
from common.time import to_utc


@dataclass(frozen=True, slots=True)
class InsightGuardrailReport:
    window_start: datetime
    window_end: datetime
    generated_count: int
    notified_count: int
    sent_delivery_count: int
    failed_delivery_count: int
    actioned_count: int
    dismissed_count: int
    expired_count: int
    false_positive_count: int
    action_rate: float | None
    dismiss_rate: float | None
    delivery_failure_rate: float | None
    false_positive_rate: float | None
    notification_enabled: bool
    guardrail_status: str
    guardrail_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "generated_count": self.generated_count,
            "notified_count": self.notified_count,
            "sent_delivery_count": self.sent_delivery_count,
            "failed_delivery_count": self.failed_delivery_count,
            "actioned_count": self.actioned_count,
            "dismissed_count": self.dismissed_count,
            "expired_count": self.expired_count,
            "false_positive_count": self.false_positive_count,
            "action_rate": self.action_rate,
            "dismiss_rate": self.dismiss_rate,
            "delivery_failure_rate": self.delivery_failure_rate,
            "false_positive_rate": self.false_positive_rate,
            "notification_enabled": self.notification_enabled,
            "guardrail_status": self.guardrail_status,
            "guardrail_reasons": list(self.guardrail_reasons),
            "missing_metrics": [],
        }


class InsightEvaluationService:
    @staticmethod
    def report(
        *,
        user: User,
        window_start: datetime,
        window_end: datetime,
        max_dismiss_rate: float | None = None,
        max_delivery_failure_rate: float | None = None,
        max_false_positive_rate: float | None = None,
    ) -> InsightGuardrailReport:
        start = to_utc(window_start)
        end = to_utc(window_end)
        if end <= start:
            raise ValueError("window_end must be later than window_start")
        for value in (
            max_dismiss_rate,
            max_delivery_failure_rate,
            max_false_positive_rate,
        ):
            if value is not None and not 0 <= value <= 1:
                raise ValueError("Guardrail rates must be between 0 and 1")

        insights = TemporalInsight.objects.filter(
            user=user, detected_at__gte=start, detected_at__lt=end
        )
        generated_count = insights.count()
        insight_ids = list(insights.values_list("id", flat=True))
        deliveries = NotificationDelivery.objects.filter(
            user=user,
            source_type=NotificationSourceType.SYSTEM,
            source_id__in=insight_ids,
            scheduled_at__gte=start,
            scheduled_at__lt=end,
        )
        notified_count = deliveries.values("source_id").distinct().count()
        sent_count = deliveries.filter(status=NotificationDeliveryStatus.SENT).count()
        failed_count = deliveries.filter(status=NotificationDeliveryStatus.FAILED).count()
        actioned_count = insights.filter(status=TemporalInsightStatus.ACTIONED).count()
        dismissed_count = insights.filter(status=TemporalInsightStatus.DISMISSED).count()
        expired_count = insights.filter(status=TemporalInsightStatus.EXPIRED).count()
        false_positive_count = insights.filter(status=TemporalInsightStatus.FALSE_POSITIVE).count()
        action_rate = _rate(actioned_count, notified_count)
        dismiss_rate = _rate(dismissed_count, notified_count)
        terminal_deliveries = sent_count + failed_count
        failure_rate = _rate(failed_count, terminal_deliveries)
        false_positive_rate = _rate(false_positive_count, generated_count)

        reasons: list[str] = []
        if generated_count == 0 or notified_count == 0:
            guardrail_status = "insufficient_data"
            reasons.append("no_notified_insights_in_window")
        elif (
            max_dismiss_rate is None
            or max_delivery_failure_rate is None
            or max_false_positive_rate is None
        ):
            guardrail_status = "not_configured"
            reasons.append("guardrail_thresholds_not_declared")
        else:
            if dismiss_rate is not None and dismiss_rate > max_dismiss_rate:
                reasons.append("dismiss_rate_exceeded")
            if failure_rate is not None and failure_rate > max_delivery_failure_rate:
                reasons.append("delivery_failure_rate_exceeded")
            if false_positive_rate is not None and false_positive_rate > max_false_positive_rate:
                reasons.append("false_positive_rate_exceeded")
            guardrail_status = "fail" if reasons else "pass"
        preference, _ = UserPreference.objects.get_or_create(user=user)
        return InsightGuardrailReport(
            window_start=start,
            window_end=end,
            generated_count=generated_count,
            notified_count=notified_count,
            sent_delivery_count=sent_count,
            failed_delivery_count=failed_count,
            actioned_count=actioned_count,
            dismissed_count=dismissed_count,
            expired_count=expired_count,
            false_positive_count=false_positive_count,
            action_rate=action_rate,
            dismiss_rate=dismiss_rate,
            delivery_failure_rate=failure_rate,
            false_positive_rate=false_positive_rate,
            notification_enabled=preference.proactive_insights_enabled,
            guardrail_status=guardrail_status,
            guardrail_reasons=tuple(reasons),
        )


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)
