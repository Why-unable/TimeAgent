from datetime import datetime
from typing import Any

from django.contrib.auth.models import User
from django.utils import timezone

from apps.events.models import CalendarEvent, CalendarEventStatus
from apps.insights.services import TemporalInsightService
from apps.preferences.services import UserPreferenceService
from apps.tasks.models import Task, TaskStatus
from common.temporal_context import TemporalContextSnapshot


class EveningBriefingService:
    """Deterministic end-of-day preview; no LLM or notification side effect."""

    @staticmethod
    def build(*, user: User, now: datetime | None = None) -> dict[str, Any]:
        preference = UserPreferenceService.get_or_create_for_user(user)
        temporal = TemporalContextSnapshot.build(
            now=now or timezone.now(), timezone_name=preference.timezone
        )
        insights = TemporalInsightService.list_open(user=user, now=temporal.now_utc)
        events = list(
            CalendarEvent.objects.filter(
                user=user,
                start_at__lt=temporal.day_end_utc,
                end_at__gt=temporal.day_start_utc,
            )
            .exclude(status=CalendarEventStatus.CANCELLED)
            .order_by("start_at", "id")
        )
        tasks = list(
            Task.objects.filter(
                user=user,
                status__in=[TaskStatus.PENDING, TaskStatus.IN_PROGRESS],
            ).filter(
                due_at__lt=temporal.day_end_utc,
            ).order_by("due_at", "id")
        )
        return {
            "target_date": temporal.local_date,
            "timezone": preference.timezone,
            "generated_at": temporal.now_utc,
            "events": [
                {
                    "id": str(event.pk),
                    "title": event.title,
                    "start_at": event.start_at,
                    "end_at": event.end_at,
                }
                for event in events
            ],
            "tasks": [
                {
                    "id": str(task.pk),
                    "title": task.title,
                    "status": task.status,
                    "due_at": task.due_at,
                    "estimated_minutes": task.estimated_minutes,
                }
                for task in tasks
            ],
            "insights": [
                {
                    "id": str(insight.pk),
                    "kind": insight.kind,
                    "severity": insight.severity,
                    "title": insight.title,
                    "summary": insight.summary,
                    "evidence": insight.evidence,
                    "expires_at": insight.expires_at,
                }
                for insight in insights
            ],
            "warnings": [],
        }
