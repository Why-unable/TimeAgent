from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.action_proposals.models import ActionProposal, ActionProposalStatus
from apps.action_proposals.services import ActionProposalService
from apps.action_proposals.tasks import expire_due_action_proposals
from apps.conversations.models import AgentRunStatus
from apps.conversations.services import AgentRunService, ConversationService, StartRunCommand
from apps.conversations.tasks import resume_agent_run_task


def _proposal(user: User) -> ActionProposal:
    conversation = ConversationService.create(user=user)
    run = AgentRunService.start(
        StartRunCommand(
            conversation=conversation,
            operation_id=uuid4(),
            request_id="approval-api",
            message="创建项目评审日程",
        )
    )
    run = AgentRunService.mark_running(run)
    run = AgentRunService.wait_for_approval(run)
    return ActionProposal.objects.create(
        user=user,
        conversation=conversation,
        agent_run=run,
        tool_call_id="create-event-api",
        original_request=run.input_message,
        explanation="创建正式日程需要审批",
        action_type="create_event",
        action_payload={"title": "项目评审"},
        original_payload={"title": "项目评审"},
        display_context={"allowed_decisions": ["approve", "edit", "reject"], "position": 0},
        expires_at=timezone.now() + timedelta(hours=1),
        idempotency_key=f"{run.pk}:create-event-api",
    )


@pytest.mark.django_db
def test_approval_api_is_user_scoped_versioned_idempotent_and_queues_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User.objects.create_user(username="approval-owner")
    other = User.objects.create_user(username="approval-other")
    proposal = _proposal(user)
    queued: list[tuple[list[str], str]] = []

    def fake_apply_async(*, args: list[str], task_id: str) -> None:
        queued.append((args, task_id))

    monkeypatch.setattr(resume_agent_run_task, "apply_async", fake_apply_async)
    client = APIClient()
    client.force_authenticate(user=other)
    assert client.get(f"/api/v1/action-proposals/{proposal.pk}/").status_code == 404

    client.force_authenticate(user=user)
    operation_id = str(uuid4())
    response = client.post(
        f"/api/v1/action-proposals/{proposal.pk}/approve/",
        {"expected_version": 1, "operation_id": operation_id},
        format="json",
    )
    assert response.status_code == 202
    assert response.json()["proposal"]["status"] == ActionProposalStatus.APPROVED
    assert response.json()["resume_queued"] is True
    assert len(queued) == 1

    replay = client.post(
        f"/api/v1/action-proposals/{proposal.pk}/approve/",
        {"expected_version": 1, "operation_id": operation_id},
        format="json",
    )
    assert replay.status_code == 202
    assert len(queued) == 1

    conflict = client.post(
        f"/api/v1/action-proposals/{proposal.pk}/reject/",
        {"expected_version": 1, "operation_id": str(uuid4())},
        format="json",
    )
    assert conflict.status_code == 409


@pytest.mark.django_db
def test_execution_failure_is_persisted_without_claiming_success() -> None:
    user = User.objects.create_user(username="approval-failure")
    proposal = _proposal(user)
    proposal.status = ActionProposalStatus.APPROVED
    proposal.save(update_fields=["status"])

    ActionProposalService.mark_executing(
        run_id=str(proposal.agent_run_id),
        tool_call_id=proposal.tool_call_id,
    )
    ActionProposalService.mark_failed(
        run_id=str(proposal.agent_run_id),
        tool_call_id=proposal.tool_call_id,
        error=RuntimeError("calendar unavailable"),
    )

    proposal.refresh_from_db()
    assert proposal.status == ActionProposalStatus.FAILED
    assert "calendar unavailable" in proposal.error
    assert proposal.executed_at is None
    assert proposal.agent_run.status == AgentRunStatus.WAITING_APPROVAL


@pytest.mark.django_db
def test_expiry_task_marks_expired_and_queues_safe_rejection_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User.objects.create_user(username="approval-expiry-task")
    proposal = _proposal(user)
    proposal.expires_at = timezone.now() - timedelta(seconds=1)
    proposal.save(update_fields=["expires_at"])
    queued: list[str] = []

    def fake_apply_async(*, args: list[str], task_id: str) -> None:
        del task_id
        queued.extend(args)

    monkeypatch.setattr(resume_agent_run_task, "apply_async", fake_apply_async)

    assert expire_due_action_proposals() == 1
    proposal.refresh_from_db()
    assert proposal.status == ActionProposalStatus.EXPIRED
    assert queued == [str(proposal.agent_run_id)]
