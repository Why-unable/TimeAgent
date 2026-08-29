from datetime import UTC, datetime, time

import pytest
from django.contrib.auth.models import User

from apps.briefings.tasks import schedule_evening_briefings
from apps.notifications.models import NotificationDelivery
from apps.preferences.services import UserPreferenceService

pytestmark = pytest.mark.django_db


def test_evening_briefing_scheduler_creates_one_idempotent_delivery() -> None:
    user = User.objects.create_user("evening-scheduler")
    preference = UserPreferenceService.get_or_create_for_user(user)
    preference.evening_briefing_enabled = True
    preference.evening_briefing_time = time(20, 0)
    preference.timezone = "UTC"
    preference.save(
        update_fields=["evening_briefing_enabled", "evening_briefing_time", "timezone"]
    )
    current = datetime(2026, 8, 24, 21, tzinfo=UTC)
    first = schedule_evening_briefings(current)
    second = schedule_evening_briefings(current)
    assert first >= 1
    assert second == 0
    assert (
        NotificationDelivery.objects.filter(
            user=user, payload__briefing_type="evening"
        ).count()
        == 1
    )
