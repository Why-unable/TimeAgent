import json
from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from apps.insights.evaluation import InsightEvaluationService
from apps.insights.models import TemporalInsight
from apps.insights.services import TemporalInsightService
from apps.notifications.models import NotificationDelivery, NotificationDeliveryStatus
from apps.preferences.services import UserPreferenceService

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 8, 24, 8, tzinfo=UTC)


def test_guardrail_report_uses_disposition_and_delivery_facts() -> None:
    user = User.objects.create_user("insight-evaluation")
    UserPreferenceService.get_or_create_for_user(user)
    insight = TemporalInsight.objects.create(
        user=user,
        kind="deadline_risk",
        severity="high",
        title="Deadline",
        summary="Deadline is near",
        evidence={"task_id": "task-1"},
        deduplication_key="evaluation:deadline",
        detected_at=NOW,
        expires_at=NOW + timedelta(days=1),
        attention_decision="NORMAL_NOTIFICATION",
        attention_reason="within_policy",
        attention_decided_at=NOW,
    )
    TemporalInsightService.materialize_notifications(user=user, now=NOW)
    delivery = NotificationDelivery.objects.get(source_id=insight.pk)
    delivery.transition_to(NotificationDeliveryStatus.QUEUED, occurred_at=NOW)
    delivery.transition_to(NotificationDeliveryStatus.SENDING, occurred_at=NOW)
    delivery.transition_to(NotificationDeliveryStatus.SENT, occurred_at=NOW)
    delivery.save()
    TemporalInsightService.act(user=user, insight_id=insight.pk, action="actioned")

    report = InsightEvaluationService.report(
        user=user,
        window_start=NOW - timedelta(minutes=1),
        window_end=NOW + timedelta(days=1),
        max_dismiss_rate=0.2,
        max_delivery_failure_rate=0.1,
        max_false_positive_rate=0.1,
    )
    assert report.action_rate == 1.0
    assert report.dismiss_rate == 0.0
    assert report.guardrail_status == "pass"
    assert report.false_positive_rate == 0.0


def test_guardrail_report_never_claims_success_without_thresholds() -> None:
    user = User.objects.create_user("insight-evaluation-no-threshold")
    UserPreferenceService.get_or_create_for_user(user)
    report = InsightEvaluationService.report(
        user=user,
        window_start=NOW,
        window_end=NOW + timedelta(days=1),
    )
    assert report.guardrail_status == "insufficient_data"


def test_guardrail_management_command_emits_machine_readable_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    user = User.objects.create_user("insight-evaluation-command")
    call_command(
        "evaluate_insight_guardrails",
        user_id=user.pk,
        window_start=NOW.isoformat(),
        window_end=(NOW + timedelta(days=1)).isoformat(),
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["guardrail_status"] == "insufficient_data"
    assert payload["missing_metrics"] == []


def test_false_positive_feedback_is_measured_and_can_fail_guardrail() -> None:
    user = User.objects.create_user("insight-evaluation-false-positive")
    UserPreferenceService.get_or_create_for_user(user)
    insight = TemporalInsight.objects.create(
        user=user,
        kind="capacity_risk",
        severity="medium",
        title="Capacity",
        summary="Capacity appears tight",
        evidence={},
        deduplication_key="evaluation:capacity",
        detected_at=NOW,
        expires_at=NOW + timedelta(days=1),
        attention_decision="NORMAL_NOTIFICATION",
        attention_reason="within_policy",
        attention_decided_at=NOW,
    )
    TemporalInsightService.materialize_notifications(user=user, now=NOW)
    TemporalInsightService.act(user=user, insight_id=insight.pk, action="false_positive")
    report = InsightEvaluationService.report(
        user=user,
        window_start=NOW - timedelta(minutes=1),
        window_end=NOW + timedelta(days=1),
        max_dismiss_rate=1,
        max_delivery_failure_rate=1,
        max_false_positive_rate=0.2,
    )
    assert report.false_positive_count == 1
    assert report.false_positive_rate == 1.0
    assert report.guardrail_status == "fail"
    assert "false_positive_rate_exceeded" in report.guardrail_reasons


def test_false_positive_rate_includes_inbox_feedback_without_delivery() -> None:
    user = User.objects.create_user("insight-evaluation-inbox-feedback")
    UserPreferenceService.get_or_create_for_user(user)
    insight = TemporalInsight.objects.create(
        user=user,
        kind="capacity_risk",
        severity="medium",
        title="Capacity",
        summary="Capacity appears tight",
        evidence={},
        deduplication_key="evaluation:inbox-capacity",
        detected_at=NOW,
        expires_at=NOW + timedelta(days=1),
        attention_decision="STORE",
        attention_reason="daily_limit",
        attention_decided_at=NOW,
    )
    TemporalInsightService.act(user=user, insight_id=insight.pk, action="false_positive")
    report = InsightEvaluationService.report(
        user=user,
        window_start=NOW - timedelta(minutes=1),
        window_end=NOW + timedelta(days=1),
        max_dismiss_rate=1,
        max_delivery_failure_rate=1,
        max_false_positive_rate=0.2,
    )
    assert report.generated_count == 1
    assert report.notified_count == 0
    assert report.false_positive_rate == 1.0
    assert report.guardrail_status == "insufficient_data"
