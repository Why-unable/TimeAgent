import logging
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.planning.adaptive import AdaptivePlanningService, ScheduleDisruption
from apps.planning.models import AutomationPolicy
from common.time import to_utc

logger = logging.getLogger(__name__)


@shared_task(name="planning.dispatch_authorized_replans")  # type: ignore[untyped-decorator]
def dispatch_authorized_replans(now: datetime | None = None) -> int:
    """Apply bounded local repairs only for explicit, no-approval task allowlists."""

    if not settings.ADAPTIVE_REPLAN_DISPATCH_ENABLED:
        return 0
    current = to_utc(now or timezone.now())
    horizon = current + timedelta(hours=settings.ADAPTIVE_REPLAN_HORIZON_HOURS)
    policies = AutomationPolicy.objects.select_related("user").filter(
        enabled=True,
        allow_task_reschedule=True,
        requires_approval=False,
    )
    applied = 0
    for policy in policies.iterator():
        authorized = set(policy.authorized_task_ids)
        if not authorized:
            continue
        disruptions = AdaptivePlanningService.detect_disruptions(
            user=policy.user,
            range_start=current,
            range_end=horizon,
        )
        moved_tasks: set[str] = set()
        for disruption in disruptions:
            task_id = str(disruption.task_id)
            if (
                task_id not in authorized
                or task_id in moved_tasks
                or len(moved_tasks) >= policy.max_moves_per_run
            ):
                continue
            try:
                preview = AdaptivePlanningService.preview_local_replan(
                    user=policy.user,
                    blocked_start=disruption.blocked_start,
                    blocked_end=disruption.blocked_end,
                    movable_task_ids=[disruption.task_id],
                    horizon_end=horizon,
                )
                if not any(item.get("state") == "moved" for item in preview.moved_items):
                    continue
                AdaptivePlanningService.apply_local_replan(
                    user=policy.user,
                    policy=policy,
                    preview=preview,
                    operation_id=_operation_id(policy=policy, disruption=disruption),
                )
            except (PermissionError, ValueError):
                logger.info(
                    "authorized_replan_skipped policy_id=%s task_id=%s",
                    policy.pk,
                    disruption.task_id,
                )
                continue
            moved_tasks.add(task_id)
            applied += 1
    return applied


def _operation_id(*, policy: AutomationPolicy, disruption: ScheduleDisruption) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        ":".join(
            (
                "time-agent",
                "authorized-replan",
                str(policy.pk),
                str(disruption.task_id),
                str(disruption.task_version),
                str(disruption.event_id),
                disruption.blocked_start.isoformat(),
            )
        ),
    )
