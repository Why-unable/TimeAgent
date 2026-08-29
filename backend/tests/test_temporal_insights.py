from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.test import Client

from apps.insights.models import TemporalInsightStatus
from apps.insights.services import TemporalInsightService
from apps.preferences.services import UserPreferenceService
from apps.tasks.services import CreateTaskCommand, TaskService

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 8, 24, 8, tzinfo=UTC)


def create_user(username: str = "insight-user") -> User:
    return get_user_model().objects.create_user(username=username)


def test_scan_creates_deduplicated_deadline_insight_and_expires_it() -> None:
    user = create_user()
    TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Submit report",
            due_at=NOW + timedelta(hours=4),
            estimated_minutes=60,
        )
    )
    first = TemporalInsightService.scan(user=user, now=NOW)
    second = TemporalInsightService.scan(user=user, now=NOW + timedelta(minutes=5))
    assert first.created_count == 1
    assert second.created_count == 0
    assert second.updated_count == 1

    insight = TemporalInsightService.list_open(user=user, now=NOW)[0]
    assert insight.kind == "deadline_risk"
    assert insight.evidence["estimated_minutes"] == 60

    TemporalInsightService.act(user=user, insight_id=insight.pk, action="dismiss")
    insight.refresh_from_db()
    assert insight.status == TemporalInsightStatus.DISMISSED


def test_insight_api_is_user_scoped_and_supports_snooze() -> None:
    user = create_user("insight-api")
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="API task", due_at=NOW + timedelta(hours=2))
    )
    client = Client()
    client.force_login(user)
    listing = client.get("/api/v1/insights/")
    insight_id = listing.json()[0]["id"]
    detail = client.get(f"/api/v1/insights/{insight_id}/")
    acted = client.post(
        f"/api/v1/insights/{insight_id}/action/",
        data={"action": "snooze", "until": (NOW + timedelta(hours=1)).isoformat()},
        content_type="application/json",
    )
    assert task.pk
    assert listing.status_code == 200
    assert detail.status_code == 200
    assert detail.json()["id"] == insight_id
    assert acted.status_code == 200
    assert acted.json()["status"] == "snoozed"


def test_scan_creates_capacity_risk_detector_with_evidence() -> None:
    user = create_user("insight-capacity")
    TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Large workload",
            due_at=NOW + timedelta(hours=4),
            estimated_minutes=3000,
        )
    )
    TemporalInsightService.scan(user=user, now=NOW)
    capacity = TemporalInsightService.list_open(user=user, now=NOW)
    capacity = [item for item in capacity if item.kind == "capacity_risk"]
    assert capacity
    assert capacity[0].evidence["unplanned_minutes"] == 3000


def test_false_positive_feedback_can_explicitly_disable_only_that_kind() -> None:
    user = create_user("insight-false-positive")
    TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Risk task",
            due_at=NOW + timedelta(hours=2),
            estimated_minutes=30,
        )
    )
    TemporalInsightService.scan(user=user, now=NOW)
    insight = next(
        item
        for item in TemporalInsightService.list_open(user=user, now=NOW)
        if item.kind == "deadline_risk"
    )
    result = TemporalInsightService.act(
        user=user,
        insight_id=insight.pk,
        action="false_positive",
        disable_kind=True,
    )
    user.preference.refresh_from_db()
    assert result.status == TemporalInsightStatus.FALSE_POSITIVE
    assert user.preference.disabled_insight_kinds == ["deadline_risk"]
    assert all(
        item.kind != "deadline_risk"
        for item in TemporalInsightService.list_open(user=user, now=NOW)
    )

    # A repeated feedback request may escalate from report-only to disabling the kind.
    UserPreferenceService.update_for_user(user, {"disabled_insight_kinds": []})
    TemporalInsightService.act(
        user=user,
        insight_id=insight.pk,
        action="false_positive",
        disable_kind=True,
    )
    user.preference.refresh_from_db()
    assert user.preference.disabled_insight_kinds == ["deadline_risk"]

    client = Client()
    client.force_login(user)
    invalid = client.post(
        f"/api/v1/insights/{insight.pk}/action/",
        data={"action": "dismiss", "disable_kind": True},
        content_type="application/json",
    )
    assert invalid.status_code == 400
