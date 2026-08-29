from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.insights.services import TemporalInsightService


@shared_task(name="insights.scan")  # type: ignore[untyped-decorator]
def scan_temporal_insights() -> int:
    """Run deterministic insight detectors for users who opted in."""
    scanned = 0
    users = get_user_model().objects.filter(preference__proactive_insights_enabled=True)
    current = timezone.now()
    for user in users.iterator():
        TemporalInsightService.scan(user=user, now=current)
        TemporalInsightService.materialize_notifications(user=user, now=current)
        scanned += 1
    return scanned
