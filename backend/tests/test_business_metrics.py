from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from prometheus_client import generate_latest

from apps.conversations.models import Conversation
from apps.conversations.services import AgentRunService, StartRunCommand
from apps.observability.metrics import _quantile
from apps.observability.models import LLMCallAudit


def test_quantile_interpolates_small_samples() -> None:
    assert _quantile([0, 0, 94], 0.95) == pytest.approx(84.6)


@pytest.mark.django_db
def test_business_metrics_expose_agent_outcomes_without_user_labels() -> None:
    user = User.objects.create_user(username="metrics-user")
    conversation = Conversation.objects.create(user=user)
    run = AgentRunService.start(
        StartRunCommand(
            conversation=conversation,
            operation_id=uuid4(),
            request_id="metrics-request",
            message="明天有什么安排？",
        )
    )
    running = AgentRunService.mark_running(run)
    running.started_at = timezone.now() - timedelta(seconds=2)
    running.save(update_fields=["started_at"])
    AgentRunService.complete(running, "没有安排。")
    LLMCallAudit.objects.create(
        request_id="private-llm-request",
        agent_run_id=str(run.pk),
        component="time_steward",
        model_name="deepseek-test",
        status="completed",
        usage_source="provider",
        input_tokens=100,
        output_tokens=20,
        total_tokens=120,
        memory_prompt_tokens=10,
        memory_prompt_ratio=0.1,
        duration_ms=500,
    )
    metrics = generate_latest().decode()
    assert 'timeagent_agent_runs_24h{status="completed",trigger_type="user_message"} 1.0' in metrics
    assert "metrics-user" not in metrics
    assert "metrics-request" not in metrics
    assert (
        'timeagent_llm_calls_24h{component="time_steward",model="deepseek-test",'
        'status="completed",usage_source="provider"} 1.0'
    ) in metrics
    assert (
        'timeagent_llm_tokens_24h{component="time_steward",direction="total",'
        'model="deepseek-test"} 120.0'
    ) in metrics
    assert (
        'timeagent_memory_prompt_ratio_24h{component="time_steward",quantile="0.95"} 0.1'
    ) in metrics
    assert "private-llm-request" not in metrics
