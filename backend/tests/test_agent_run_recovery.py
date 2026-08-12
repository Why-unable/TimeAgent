from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.conversations.models import AgentRun, AgentRunStatus, Conversation
from apps.conversations.services import AgentRunService, StartRunCommand

pytestmark = pytest.mark.django_db


def test_stale_agent_runs_are_failed_without_overwriting_terminal_runs() -> None:
    user = User.objects.create_user(username="stale-run-user")
    conversation = Conversation.objects.create(user=user)
    stale = AgentRunService.start(
        StartRunCommand(
            conversation=conversation,
            operation_id=uuid4(),
            request_id="stale-request",
            message="安排一下明天",
        )
    )
    AgentRunService.mark_running(stale)
    old = timezone.now() - timedelta(minutes=20)
    AgentRun.objects.filter(pk=stale.pk).update(created_at=old, started_at=old)

    recovered = AgentRunService.fail_stale_runs(cutoff=timezone.now() - timedelta(minutes=10))

    stale.refresh_from_db()
    assert recovered == 1
    assert stale.status == AgentRunStatus.FAILED
    assert stale.completed_at is not None
    event = stale.events.get(event_type="run.failed")
    assert event.payload["error_code"] == "agent_execution_stale"
