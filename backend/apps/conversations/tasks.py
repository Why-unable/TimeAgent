from uuid import UUID

from celery import shared_task

from apps.conversations.execution import execute_agent_run, resume_agent_run
from apps.conversations.models import AgentRun


@shared_task(
    bind=True,
    name="conversations.execute_agent_run",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=180,
    time_limit=195,
)  # type: ignore[untyped-decorator]
def execute_agent_run_task(self: object, run_id: str) -> str:
    """Execute a persisted AgentRun outside the request-response lifecycle."""

    run = AgentRun.objects.select_related("conversation__user").get(pk=UUID(run_id))
    task_id = str(getattr(getattr(self, "request", None), "id", "") or "")
    result = execute_agent_run(run, actor=run.conversation.user, task_id=task_id)
    return result.status


@shared_task(
    bind=True,
    name="conversations.resume_agent_run",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=180,
    time_limit=195,
)  # type: ignore[untyped-decorator]
def resume_agent_run_task(self: object, run_id: str) -> str:
    run = AgentRun.objects.select_related("conversation__user").get(pk=UUID(run_id))
    task_id = str(getattr(getattr(self, "request", None), "id", "") or "")
    result = resume_agent_run(
        run,
        actor=run.conversation.user,
        task_id=task_id,
    )
    return result.status
