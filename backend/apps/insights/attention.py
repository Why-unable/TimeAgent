from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User

from apps.insights.models import TemporalInsight
from apps.notifications.models import NotificationDelivery, NotificationDeliveryStatus
from apps.preferences.services import UserPreferenceService


@dataclass(frozen=True, slots=True)
class AttentionDecision:
    decision: str
    reason: str


class AttentionPolicy:
    @staticmethod
    def decide(*, user: User, insight: TemporalInsight, now: datetime) -> AttentionDecision:
        preference = UserPreferenceService.get_or_create_for_user(user)
        if not preference.proactive_insights_enabled:
            return AttentionDecision("STORE", "user_disabled")
        if insight.kind in preference.disabled_insight_kinds:
            return AttentionDecision("STORE", "kind_disabled")
        local_now = now.astimezone(ZoneInfo(preference.timezone))
        current_time = local_now.timetz().replace(tzinfo=None)
        if AttentionPolicy._in_quiet_hours(
            current_time, preference.sleep_start, preference.sleep_end
        ):
            return AttentionDecision("STORE", "quiet_hours")
        local_date = local_now.date()
        day_start = datetime.combine(local_date, time.min, tzinfo=local_now.tzinfo)
        day_end = day_start + timedelta(days=1)
        deliveries_today = NotificationDelivery.objects.filter(
            user=user,
            source_type="system",
            status__in=[
                NotificationDeliveryStatus.PENDING,
                NotificationDeliveryStatus.QUEUED,
                NotificationDeliveryStatus.SENDING,
                NotificationDeliveryStatus.SENT,
            ],
            scheduled_at__gte=day_start,
            scheduled_at__lt=day_end,
        )
        sent_today = sum(1 for delivery in deliveries_today if delivery.payload.get("insight_id"))
        if sent_today >= preference.insight_daily_notification_limit:
            return AttentionDecision("STORE", "daily_limit")
        cooldown_since = now - timedelta(minutes=preference.insight_cooldown_minutes)
        recent_deliveries = NotificationDelivery.objects.filter(
            user=user,
            source_type="system",
            status__in=[
                NotificationDeliveryStatus.QUEUED,
                NotificationDeliveryStatus.SENDING,
                NotificationDeliveryStatus.SENT,
            ],
            scheduled_at__gte=cooldown_since,
        )
        recent_same_kind = any(
            delivery.payload.get("insight_kind") == insight.kind for delivery in recent_deliveries
        )
        if recent_same_kind:
            return AttentionDecision("STORE", "kind_cooldown")
        if insight.severity == "high":
            return AttentionDecision("HIGH_PRIORITY_NOTIFICATION", "high_severity")
        return AttentionDecision("NORMAL_NOTIFICATION", "within_policy")

    @staticmethod
    def _in_quiet_hours(current: time, start: time, end: time) -> bool:
        if start == end:
            return True
        if start < end:
            return start <= current < end
        return current >= start or current < end
