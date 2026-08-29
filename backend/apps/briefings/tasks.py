from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.briefings.evening import EveningBriefingService
from apps.briefings.scheduling import DailyBriefingScheduler
from apps.conversations.services import AgentRunService
from apps.conversations.tasks import execute_agent_run_task
from apps.notifications.models import NotificationDelivery, NotificationSourceType
from apps.notifications.services import CreateDeliveryCommand, NotificationService
from apps.preferences.services import UserPreferenceService
from common.temporal_context import TemporalContextSnapshot

logger = logging.getLogger(__name__)


@shared_task(name="briefings.schedule_due")  # type: ignore[untyped-decorator]
def schedule_due_daily_briefings() -> int:
    queued = 0
    for due in DailyBriefingScheduler.due(now=timezone.now()):
        run, created = DailyBriefingScheduler.prepare(due)
        if not created:
            continue
        task_id = str(uuid4())
        if not AgentRunService.reserve_execution_task(run, task_id):
            continue
        try:
            execute_agent_run_task.apply_async(args=[str(run.pk)], task_id=task_id)
        except Exception:
            AgentRunService.release_execution_task(run, task_id)
            logger.exception(
                "scheduled_briefing_queue_failed run_id=%s user_id=%s delivery_at=%s",
                run.pk,
                run.conversation.user_id,
                due.delivery_at.isoformat(),
            )
            continue
        queued += 1
    return queued


@shared_task(name="briefings.schedule_evening")  # type: ignore[untyped-decorator]
def schedule_evening_briefings(now: datetime | None = None) -> int:
    created = 0
    now = now or timezone.now()
    users = get_user_model().objects.filter(preference__evening_briefing_enabled=True)
    for user in users.iterator():
        preference = UserPreferenceService.get_or_create_for_user(user)
        temporal = TemporalContextSnapshot.build(now=now, timezone_name=preference.timezone)
        local_time = temporal.now_utc.astimezone(ZoneInfo(preference.timezone)).time()
        if local_time < preference.evening_briefing_time:
            continue
        report = EveningBriefingService.build(user=user, now=temporal.now_utc)
        body = _render_evening_briefing(report)
        for channel in NotificationService.channels_for(
            user=user, source_type=NotificationSourceType.BRIEFING
        ):
            deduplication_key = (
                f"evening-briefing:{temporal.local_date.isoformat()}:{channel}"
            )
            already_exists = NotificationDelivery.objects.filter(
                user=user, deduplication_key=deduplication_key
            ).exists()
            NotificationService.create_delivery(
                CreateDeliveryCommand(
                    user=user,
                    source_type=NotificationSourceType.SYSTEM,
                    source_id=None,
                    channel_type=channel,
                    deduplication_key=deduplication_key,
                    subject=f"{temporal.local_date.isoformat()} 今日收尾",
                    body=body,
                    scheduled_at=temporal.day_start_utc,
                    payload={
                        "briefing_type": "evening",
                        "target_date": temporal.local_date.isoformat(),
                        "task_count": len(report["tasks"]),
                        "insight_count": len(report["insights"]),
                    },
                )
            )
            if not already_exists:
                created += 1
    return created


def _render_evening_briefing(report: dict[str, object]) -> str:
    tasks = report["tasks"]
    insights = report["insights"]
    task_count = len(tasks) if isinstance(tasks, list) else 0
    insight_count = len(insights) if isinstance(insights, list) else 0
    return f"今日收尾：{task_count} 个未完成/到期任务，{insight_count} 条需要留意的洞察。"
