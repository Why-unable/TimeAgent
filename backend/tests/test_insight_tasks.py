from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth.models import User

from apps.insights.models import TemporalInsight
from apps.insights.tasks import scan_temporal_insights
from apps.preferences.services import UserPreferenceService
from apps.tasks.services import CreateTaskCommand, TaskService

pytestmark = pytest.mark.django_db


def test_scheduled_insight_scan_is_deterministic_and_respects_opt_out() -> None:
    now = datetime(2026, 8, 24, 8, tzinfo=UTC)
    opted_in = User.objects.create_user("scan-in")
    opted_out = User.objects.create_user("scan-out")
    UserPreferenceService.get_or_create_for_user(opted_in)
    preference = UserPreferenceService.get_or_create_for_user(opted_out)
    preference.proactive_insights_enabled = False
    preference.save(update_fields=["proactive_insights_enabled"])
    for user in [opted_in, opted_out]:
        TaskService.create_task(
            CreateTaskCommand(
                user=user,
                title="Upcoming",
                due_at=now + timedelta(hours=2),
            )
        )

    assert scan_temporal_insights() == 1
    assert TemporalInsight.objects.filter(user=opted_in).count() == 1
    assert TemporalInsight.objects.filter(user=opted_out).count() == 0
