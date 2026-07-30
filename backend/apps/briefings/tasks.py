from __future__ import annotations

import logging
from uuid import uuid4

from celery import shared_task
from django.utils import timezone

from apps.briefings.scheduling import DailyBriefingScheduler
from apps.conversations.services import AgentRunService
from apps.conversations.tasks import execute_agent_run_task

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
