from uuid import uuid4

from celery import shared_task

from apps.action_proposals.services import ActionProposalService
from apps.conversations.models import AgentRun
from apps.conversations.services import AgentRunService
from apps.conversations.tasks import resume_agent_run_task


@shared_task(name="action_proposals.expire_due")  # type: ignore[untyped-decorator]
def expire_due_action_proposals() -> int:
    run_ids = ActionProposalService.expire_due_runs()
    for run_id in run_ids:
        if not ActionProposalService.resume_ready(run_id):
            continue
        run = AgentRun.objects.get(pk=run_id)
        task_id = str(uuid4())
        if not AgentRunService.reserve_resume_task(run, task_id):
            continue
        try:
            resume_agent_run_task.apply_async(args=[str(run_id)], task_id=task_id)
        except Exception:
            AgentRunService.release_resume_task(run, task_id)
            raise
    return len(run_ids)
