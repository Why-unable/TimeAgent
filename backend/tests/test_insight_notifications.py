from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth.models import User

from apps.insights.models import TemporalInsight
from apps.insights.services import TemporalInsightService
from apps.notifications.models import (
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationSourceType,
)
from apps.preferences.services import UserPreferenceService
from apps.tasks.services import CreateTaskCommand, TaskService

pytestmark = pytest.mark.django_db


def test_approved_insight_notification_materialization_is_idempotent() -> None:
    user = User.objects.create_user("insight-delivery")
    UserPreferenceService.get_or_create_for_user(user)
    insight = TemporalInsight.objects.create(
        user=user,
        kind="deadline_risk",
        severity="medium",
        title="Deadline",
        summary="Deadline is near",
        evidence={"task_id": "task-1"},
        deduplication_key="deadline:task-1",
        detected_at=datetime(2026, 8, 24, 8, tzinfo=UTC),
        expires_at=datetime(2026, 8, 25, 8, tzinfo=UTC),
        attention_decision="NORMAL_NOTIFICATION",
        attention_reason="within_policy",
        attention_decided_at=datetime(2026, 8, 24, 8, tzinfo=UTC),
    )
    first = TemporalInsightService.materialize_notifications(
        user=user, now=datetime(2026, 8, 24, 8, tzinfo=UTC)
    )
    second = TemporalInsightService.materialize_notifications(
        user=user, now=datetime(2026, 8, 24, 8, tzinfo=UTC) + timedelta(minutes=1)
    )
    assert first >= 1
    assert second == 0
    assert NotificationDelivery.objects.filter(
        user=user, source_type=NotificationSourceType.SYSTEM, source_id=insight.pk
    ).exists()
    delivery = NotificationDelivery.objects.get(
        user=user, source_type=NotificationSourceType.SYSTEM, source_id=insight.pk
    )
    assert delivery.deduplication_key == f"insight:v2:{insight.pk}:console"
    assert delivery.payload["url"] == f"/insights/{insight.pk}"


def test_rescan_preserves_notification_time_anchor() -> None:
    user = User.objects.create_user("insight-rescan")
    UserPreferenceService.get_or_create_for_user(user)
    first_scan = datetime(2026, 8, 24, 8, tzinfo=UTC)
    TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Stable deadline",
            due_at=first_scan + timedelta(hours=2),
        )
    )

    TemporalInsightService.scan(user=user, now=first_scan)
    assert TemporalInsightService.materialize_notifications(user=user, now=first_scan) == 1
    insight = TemporalInsight.objects.get(user=user)
    original_detected_at = insight.detected_at
    original_decided_at = insight.attention_decided_at

    TemporalInsightService.scan(user=user, now=first_scan + timedelta(minutes=5))
    assert TemporalInsightService.materialize_notifications(
        user=user, now=first_scan + timedelta(minutes=5)
    ) == 0
    insight.refresh_from_db()
    assert insight.detected_at == original_detected_at
    assert insight.attention_decided_at == original_decided_at


def test_legacy_insight_delivery_is_not_duplicated_on_payload_upgrade() -> None:
    user = User.objects.create_user("insight-legacy-delivery")
    UserPreferenceService.get_or_create_for_user(user)
    decided_at = datetime(2026, 8, 24, 8, tzinfo=UTC)
    insight = TemporalInsight.objects.create(
        user=user,
        kind="deadline_risk",
        severity="medium",
        title="Legacy deadline",
        summary="Deadline is near",
        evidence={},
        deduplication_key="deadline:legacy",
        detected_at=decided_at,
        expires_at=decided_at + timedelta(days=1),
        attention_decision="NORMAL_NOTIFICATION",
        attention_reason="within_policy",
        attention_decided_at=decided_at,
    )
    NotificationDelivery.objects.create(
        user=user,
        source_type=NotificationSourceType.SYSTEM,
        source_id=insight.pk,
        channel_type="console",
        deduplication_key=f"insight:{insight.pk}:console",
        subject=insight.title,
        body=insight.summary,
        payload={"url": "/today"},
        scheduled_at=decided_at - timedelta(minutes=1),
    )

    assert TemporalInsightService.materialize_notifications(user=user, now=decided_at) == 0
    assert NotificationDelivery.objects.filter(user=user, source_id=insight.pk).count() == 1


def test_false_positive_cancels_pending_delivery_and_disabled_kind_is_not_materialized() -> None:
    user = User.objects.create_user("insight-delivery-feedback")
    UserPreferenceService.get_or_create_for_user(user)
    insight = TemporalInsight.objects.create(
        user=user,
        kind="deadline_risk",
        severity="medium",
        title="Deadline",
        summary="Deadline is near",
        evidence={},
        deduplication_key="deadline:feedback",
        detected_at=datetime(2026, 8, 24, 8, tzinfo=UTC),
        expires_at=datetime(2026, 8, 25, 8, tzinfo=UTC),
        attention_decision="NORMAL_NOTIFICATION",
        attention_reason="within_policy",
        attention_decided_at=datetime(2026, 8, 24, 8, tzinfo=UTC),
    )
    TemporalInsightService.materialize_notifications(user=user)
    TemporalInsightService.act(
        user=user,
        insight_id=insight.pk,
        action="false_positive",
        disable_kind=True,
    )
    delivery = NotificationDelivery.objects.get(source_id=insight.pk)
    assert delivery.status == NotificationDeliveryStatus.CANCELLED

    another = TemporalInsight.objects.create(
        user=user,
        kind="deadline_risk",
        severity="high",
        title="Another deadline",
        summary="Another deadline is near",
        evidence={},
        deduplication_key="deadline:disabled",
        detected_at=datetime(2026, 8, 24, 9, tzinfo=UTC),
        expires_at=datetime(2026, 8, 25, 9, tzinfo=UTC),
        attention_decision="HIGH_PRIORITY_NOTIFICATION",
        attention_reason="high_severity",
        attention_decided_at=datetime(2026, 8, 24, 9, tzinfo=UTC),
    )
    assert TemporalInsightService.materialize_notifications(user=user) == 0
    assert not NotificationDelivery.objects.filter(source_id=another.pk).exists()
