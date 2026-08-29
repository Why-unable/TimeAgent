from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.test import override_settings

from apps.conversations.event_stream import RedisAgentEventStream
from apps.conversations.models import Conversation
from apps.conversations.services import AgentRunService, StartRunCommand


@pytest.mark.django_db(transaction=True)
def test_append_event_publishes_only_after_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    user = User.objects.create_user(username=f"stream-{uuid4()}")
    conversation = Conversation.objects.create(user=user)
    run = AgentRunService.start(
        StartRunCommand(
            conversation=conversation,
            operation_id=uuid4(),
            request_id="test-stream",
            message="hello",
        )
    )
    publisher = Mock()
    monkeypatch.setattr("apps.conversations.services.publish_agent_event", publisher)

    event = AgentRunService.append_event(run, "agent.started", {"ok": True})

    publisher.assert_called_once_with(
        run_id=event.run_id,
        sequence=event.sequence,
        event_type="agent.started",
        payload={"ok": True},
        created_at=event.created_at,
    )


@override_settings(AGENT_EVENT_STREAM_ENABLED=True)
def test_publish_failure_is_best_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    client.xadd.side_effect = RuntimeError("redis down")
    monkeypatch.setattr("apps.conversations.event_stream.Redis.from_url", lambda *a, **k: client)

    assert RedisAgentEventStream("redis://unused").publish(
        run_id=uuid4(),
        sequence=1,
        event_type="agent.started",
        payload={},
        created_at=datetime.now(UTC),
    ) is False


@override_settings(AGENT_EVENT_STREAM_ENABLED=True)
def test_publish_writes_complete_sse_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    monkeypatch.setattr("apps.conversations.event_stream.Redis.from_url", lambda *a, **k: client)
    created_at = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)

    assert RedisAgentEventStream("redis://unused").publish(
        run_id="run-1",
        sequence=7,
        event_type="tool.completed",
        payload={"value": "ok"},
        created_at=created_at,
    ) is True

    key, fields = client.xadd.call_args.args
    assert key == "timeagent:agent-events:run-1"
    assert fields["sequence"] == "7"
    assert fields["event_type"] == "tool.completed"
    assert fields["payload"] == '{"value":"ok"}'
    assert fields["created_at"] == created_at.isoformat()
    client.expire.assert_called_once()
