from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from asgiref.sync import async_to_sync
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
    monkeypatch.setattr("apps.conversations.event_stream._sync_client", lambda url: client)

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
    monkeypatch.setattr("apps.conversations.event_stream._sync_client", lambda url: client)
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


@override_settings(AGENT_EVENT_STREAM_ENABLED=True)
def test_empty_stream_uses_replayable_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    client.xrevrange.return_value = []
    monkeypatch.setattr("apps.conversations.event_stream._sync_client", lambda url: client)

    assert RedisAgentEventStream("redis://unused").baseline_sync(run_id="run-1") == "0-0"


def test_sse_reconciles_sequence_gap_from_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.conversations import views

    first_run = SimpleNamespace(status="running", execution_task_id="task")
    terminal_run = SimpleNamespace(status="completed", execution_task_id=None)
    missing = SimpleNamespace(
        sequence=1,
        event_type="agent.started",
        payload={"n": 1},
        created_at=datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
    )
    calls = 0

    def poll(**_: object) -> tuple[object, list[object]]:
        nonlocal calls
        calls += 1
        return (first_run, [missing]) if calls == 1 else (terminal_run, [])

    class FakeStream:
        async def read(self, **_: object):
            yield {
                "redis_id": "2-0",
                "sequence": 2,
                "event_type": "agent.completed",
                "payload": {"n": 2},
                "created_at": "2026-08-29T12:00:01+00:00",
            }

    monkeypatch.setattr(views, "_sse_poll", poll)
    monkeypatch.setattr(views, "RedisAgentEventStream", FakeStream)
    async def collect() -> list[bytes]:
        return [
            frame
            async for frame in views._sse(
                user_id=1,
                run_id=uuid4(),
                cursor=0,
                initial_snapshot=(first_run, []),
                stream_baseline="0-0",
            )
        ]

    frames = async_to_sync(collect)()

    assert b"id: 1" in frames[0]
    assert b"id: 2" in frames[1]


def test_sse_falls_back_to_postgres_when_redis_read_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.conversations import views

    run = SimpleNamespace(status="running", execution_task_id="task")
    terminal = SimpleNamespace(status="completed", execution_task_id=None)
    event = SimpleNamespace(
        sequence=1,
        event_type="agent.started",
        payload={"source": "postgres"},
        created_at=datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
    )
    poll_calls = 0

    def poll(**_: object) -> tuple[object, list[object]]:
        nonlocal poll_calls
        poll_calls += 1
        return (run, []) if poll_calls == 1 else (terminal, [event])

    class BrokenStream:
        async def read(self, **_: object):
            raise ConnectionError("redis unavailable")
            yield  # pragma: no cover

    monkeypatch.setattr(views, "_sse_poll", poll)
    monkeypatch.setattr(views, "RedisAgentEventStream", BrokenStream)

    async def collect() -> list[bytes]:
        return [
            frame
            async for frame in views._sse(
                user_id=1,
                run_id=uuid4(),
                cursor=0,
                initial_snapshot=(run, []),
                stream_baseline="0-0",
            )
        ]

    frames = async_to_sync(collect)()
    assert len(frames) == 1
    assert b"id: 1" in frames[0]
    assert b'"source":"postgres"' in frames[0]
