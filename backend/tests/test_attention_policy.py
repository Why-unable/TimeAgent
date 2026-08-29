from datetime import UTC, datetime

import pytest
from django.contrib.auth.models import User

from apps.insights.attention import AttentionPolicy
from apps.insights.models import TemporalInsight
from apps.notifications.models import (
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationSourceType,
)
from apps.preferences.services import UserPreferenceService

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 8, 24, 8, tzinfo=UTC)


def make_insight(user: User, *, severity: str = "medium") -> TemporalInsight:
    return TemporalInsight(
        user=user,
        kind="deadline_risk",
        severity=severity,
        title="Deadline",
        summary="Deadline is near",
        evidence={"task_id": "task-1"},
        deduplication_key="deadline:task-1",
        detected_at=NOW,
        expires_at=datetime(2026, 8, 26, tzinfo=UTC),
    )


def test_attention_policy_respects_user_disabled_and_quiet_hours() -> None:
    user = User.objects.create_user("attention-user")
    preference = UserPreferenceService.get_or_create_for_user(user)
    insight = make_insight(user)

    preference.proactive_insights_enabled = False
    preference.save(update_fields=["proactive_insights_enabled"])
    assert AttentionPolicy.decide(user=user, insight=insight, now=NOW).reason == "user_disabled"

    preference.proactive_insights_enabled = True
    preference.sleep_start = preference.sleep_end = preference.sleep_start
    preference.save(update_fields=["proactive_insights_enabled", "sleep_start", "sleep_end"])
    assert AttentionPolicy.decide(user=user, insight=insight, now=NOW).reason == "quiet_hours"


def test_attention_policy_respects_explicit_kind_disable() -> None:
    user = User.objects.create_user("attention-kind-disabled")
    preference = UserPreferenceService.get_or_create_for_user(user)
    preference.disabled_insight_kinds = ["deadline_risk"]
    preference.save(update_fields=["disabled_insight_kinds"])
    assert (
        AttentionPolicy.decide(user=user, insight=make_insight(user), now=NOW).reason
        == "kind_disabled"
    )


def test_attention_policy_enforces_daily_limit_and_kind_cooldown() -> None:
    user = User.objects.create_user("attention-limit")
    preference = UserPreferenceService.get_or_create_for_user(user)
    preference.insight_daily_notification_limit = 1
    preference.insight_cooldown_minutes = 240
    preference.save(update_fields=["insight_daily_notification_limit", "insight_cooldown_minutes"])
    insight = make_insight(user)

    existing = NotificationDelivery.objects.create(
        user=user,
        source_type=NotificationSourceType.SYSTEM,
        channel_type="console",
        deduplication_key="insight:existing",
        subject="Existing insight",
        body="Existing insight",
        payload={"insight_id": "existing", "insight_kind": "other"},
        scheduled_at=NOW,
    )
    existing.transition_to(NotificationDeliveryStatus.QUEUED, occurred_at=NOW)
    existing.save(update_fields=["status", "queued_at", "updated_at"])
    assert AttentionPolicy.decide(user=user, insight=insight, now=NOW).reason == "daily_limit"

    preference.insight_daily_notification_limit = 3
    preference.save(update_fields=["insight_daily_notification_limit"])
    same_kind = NotificationDelivery.objects.create(
        user=user,
        source_type=NotificationSourceType.SYSTEM,
        channel_type="console",
        deduplication_key="insight:same-kind",
        subject="Same kind",
        body="Same kind",
        payload={"insight_id": "same", "insight_kind": insight.kind},
        scheduled_at=NOW,
    )
    same_kind.transition_to(NotificationDeliveryStatus.QUEUED, occurred_at=NOW)
    same_kind.save(update_fields=["status", "queued_at", "updated_at"])
    assert AttentionPolicy.decide(user=user, insight=insight, now=NOW).reason == "kind_cooldown"
