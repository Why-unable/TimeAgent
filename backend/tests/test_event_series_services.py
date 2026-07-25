from datetime import UTC, datetime

import pytest
from django.contrib.auth import get_user_model

from apps.events.models import CalendarEventStatus, EventSeriesStatus
from apps.events.series_services import CreateEventSeriesCommand, EventSeriesService

pytestmark = pytest.mark.django_db


def test_create_and_cancel_finite_event_series_is_atomic() -> None:
    user = get_user_model().objects.create_user(username="series-user")
    series = EventSeriesService.create_series(
        CreateEventSeriesCommand(
            user=user,
            title="Morning review",
            start_at=datetime(2026, 7, 27, 1, tzinfo=UTC),
            end_at=datetime(2026, 7, 27, 2, tzinfo=UTC),
            timezone="Asia/Shanghai",
            frequency="daily",
            occurrence_count=3,
        )
    )

    assert series.occurrences.count() == 3
    cancelled = EventSeriesService.cancel_series(series=series, user=user)
    assert cancelled.status == EventSeriesStatus.CANCELLED
    assert set(cancelled.occurrences.values_list("status", flat=True)) == {
        CalendarEventStatus.CANCELLED
    }
