from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.db import OperationalError, connections
from django.http import StreamingHttpResponse
from langchain_core.messages import AIMessage, AIMessageChunk
from rest_framework.test import APIClient

from apps.conversations.execution import _last_ai_text, _message_text, _stream_mode_data
from apps.conversations.models import AgentRun, Conversation
from apps.conversations.services import (
    AgentRunService,
    StartRunCommand,
    ToolAuditService,
    classify_agent_run_failure,
)
from apps.conversations.tasks import execute_agent_run_task


async def _collect_async_stream(stream: StreamingHttpResponse) -> bytes:
    content = cast("AsyncIterator[bytes]", stream.streaming_content)
    return b"".join([item async for item in content])


def test_native_subgraph_stream_shape_is_normalized() -> None:
    message = AIMessage(content="delta")
    chunk = AIMessageChunk(content=[{"type": "text", "text": "block delta", "index": 0}])
    assert _stream_mode_data((("agent:1",), (message, {"node": "model"}))) == (
        "messages",
        (message, {"node": "model"}),
    )
    assert _stream_mode_data((chunk, {"node": "model"})) == (
        "messages",
        (chunk, {"node": "model"}),
    )
    assert _stream_mode_data(((), {"messages": [message]})) == (
        "values",
        {"messages": [message]},
    )
    assert _message_text(chunk) == "block delta"


def test_sse_connection_cleanup_preserves_connections_inside_transactions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.conversations.views import _close_stale_sse_connections

    closed: list[str] = []
    transactional = SimpleNamespace(
        in_atomic_block=True,
        close_if_unusable_or_obsolete=lambda: closed.append("transactional"),
    )
    idle = SimpleNamespace(
        in_atomic_block=False,
        close_if_unusable_or_obsolete=lambda: closed.append("idle"),
    )
    monkeypatch.setattr(connections, "all", lambda **_: [transactional, idle])

    _close_stale_sse_connections()

    assert closed == ["idle"]


def test_final_ai_message_accepts_content_blocks() -> None:
    assert (
        _last_ai_text({"messages": [AIMessage(content=[{"type": "text", "text": "done"}])]})
        == "done"
    )


def test_empty_final_ai_message_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="empty final AI message"):
        _last_ai_text({"messages": [AIMessage(content="")]})


def test_agent_failures_are_safe_specific_and_retryable() -> None:
    timeout = classify_agent_run_failure(TimeoutError("secret upstream detail"))
    assert timeout.code == "model_timeout"
    assert timeout.retryable is True
    assert "secret" not in timeout.message

    class AuthenticationError(Exception):
        pass

    authentication = classify_agent_run_failure(AuthenticationError("invalid api key: secret"))
    assert authentication.code == "model_authentication_failed"
    assert "secret" not in authentication.message

    deadlock = classify_agent_run_failure(OperationalError("deadlock detected"))
    assert deadlock.code == "database_concurrency_conflict"
    assert deadlock.retryable is True


@pytest.mark.django_db
def test_failed_run_reports_partial_success_after_completed_write() -> None:
    user = User.objects.create_user(username="partial-agent-run")
    run = AgentRunService.start(
        StartRunCommand(
            conversation=Conversation.objects.create(user=user),
            operation_id=uuid4(),
            request_id="partial-request",
            message="创建日程并设置提醒",
        )
    )
    run = AgentRunService.mark_running(run)
    audit, created = ToolAuditService.begin(
        run_id=str(run.pk),
        user=user,
        tool_call_id="completed-write",
        tool_name="mutate_events",
        arguments={},
        risk_level="high",
    )
    assert created is True
    ToolAuditService.complete(audit, [{"id": "event-id"}])

    failed = AgentRunService.fail(run, OperationalError("deadlock detected"))

    assert failed.status == "failed"
    assert "仅部分完成" in failed.error
    assert "并发冲突" in failed.error
    event = failed.events.get(event_type="run.failed")
    assert event.payload["partial_success"] is True
    assert event.payload["completed_write_tools"] == ["mutate_events"]
    assert event.payload["error_code"] == "database_concurrency_conflict"


@pytest.mark.django_db
def test_run_anchor_is_captured_once_and_idempotently_reused() -> None:
    user = User.objects.create_user(username="run-anchor")
    conversation = Conversation.objects.create(user=user)
    operation_id = uuid4()
    first_anchor = datetime(2026, 8, 12, 0, tzinfo=UTC)
    command = StartRunCommand(
        conversation=conversation,
        operation_id=operation_id,
        request_id="anchor-request",
        message="一天后创建日程",
        anchor_at=first_anchor,
        anchor_timezone="Asia/Shanghai",
    )

    created = AgentRunService.start(command)
    replayed = AgentRunService.start(
        StartRunCommand(
            conversation=conversation,
            operation_id=operation_id,
            request_id="anchor-request-retry",
            message="一天后创建日程",
            anchor_at=datetime(2026, 8, 12, 2, tzinfo=UTC),
            anchor_timezone="UTC",
        )
    )

    assert created.pk == replayed.pk
    assert replayed.anchor_at == first_anchor
    assert replayed.anchor_timezone == "Asia/Shanghai"


@pytest.mark.django_db
def test_chat_run_lifecycle_and_sse_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    user = User.objects.create_user(username="chat-user")
    client = APIClient()
    client.force_authenticate(user=user)
    conversation_response = client.post(
        "/api/v1/chat/conversations/", {"title": "Planning"}, format="json"
    )
    conversation_id = conversation_response.json()["id"]

    queued: list[dict[str, object]] = []

    def fake_apply_async(*, args: list[str], task_id: str) -> None:
        queued.append({"args": args, "task_id": task_id})

    monkeypatch.setattr(execute_agent_run_task, "apply_async", fake_apply_async)

    def fake_execute(run: AgentRun) -> AgentRun:
        running = AgentRunService.claim_for_execution(run, task_id=run.execution_task_id)
        assert running is not None
        AgentRunService.append_event(
            running,
            "tool.started",
            {"tool_call_id": "tool-1", "tool_name": "list_events"},
        )
        AgentRunService.append_event(
            running,
            "tool.completed",
            {"tool_call_id": "tool-1", "tool_name": "list_events"},
        )
        return AgentRunService.complete(running, "你今天没有安排。")

    operation_id = str(uuid4())
    response = client.post(
        "/api/v1/chat/messages/",
        {
            "conversation_id": conversation_id,
            "message": "今天有什么安排？",
            "operation_id": operation_id,
        },
        format="json",
        HTTP_X_REQUEST_ID="request-chat-1",
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["final_response"] == ""
    assert body["operation_id"] == operation_id
    assert queued[0]["args"] == [body["id"]]
    assert queued[0]["task_id"] == AgentRun.objects.get(pk=body["id"]).execution_task_id

    duplicate = client.post(
        "/api/v1/chat/messages/",
        {
            "conversation_id": conversation_id,
            "message": "今天有什么安排？",
            "operation_id": operation_id,
        },
        format="json",
    )
    assert duplicate.status_code == 202
    assert duplicate.json()["id"] == body["id"]
    assert len(queued) == 1

    completed = fake_execute(AgentRun.objects.get(pk=body["id"]))
    assert completed.status == "completed"

    stream = client.get(
        f"/api/v1/chat/runs/{body['id']}/events/?cursor=1",
        HTTP_ACCEPT="text/event-stream",
    )
    assert isinstance(stream, StreamingHttpResponse)
    content = async_to_sync(_collect_async_stream)(stream)
    assert b"id: 1\n" not in content
    assert b"event: tool.started" in content
    assert b"event: tool.completed" in content
    assert b"event: message.completed" in content
    assert "你今天没有安排。".encode() in content
    assert b'"event_created_at":' in content


@pytest.mark.django_db
def test_conversation_history_is_scoped_ordered_and_updates_recency() -> None:
    user = User.objects.create_user(username="history-user")
    other_user = User.objects.create_user(username="other-history-user")
    client = APIClient()
    client.force_authenticate(user=user)
    conversation = Conversation.objects.create(user=user)
    other_conversation = Conversation.objects.create(user=other_user, title="private")

    first = AgentRunService.start(
        StartRunCommand(
            conversation=conversation,
            operation_id=uuid4(),
            request_id="history-1",
            message="今天有什么安排？",
        )
    )
    first = AgentRunService.complete(AgentRunService.mark_running(first), "下午三点开会。")
    second = AgentRunService.start(
        StartRunCommand(
            conversation=conversation,
            operation_id=uuid4(),
            request_id="history-2",
            message="提醒我提前十分钟准备。",
        )
    )

    detail = client.get(f"/api/v1/chat/conversations/{conversation.pk}/")

    assert detail.status_code == 200
    body = detail.json()
    assert body["title"] == "今天有什么安排？"
    assert [run["id"] for run in body["runs"]] == [str(first.pk), str(second.pk)]
    assert body["runs"][0]["final_response"] == "下午三点开会。"
    assert body["runs"][1]["input_message"] == "提醒我提前十分钟准备。"
    assert client.get(f"/api/v1/chat/conversations/{other_conversation.pk}/").status_code == 404

    listed = client.get("/api/v1/chat/conversations/").json()
    assert [item["id"] for item in listed] == [str(conversation.pk)]


@pytest.mark.django_db
def test_chat_releases_task_reservation_when_queue_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User.objects.create_user(username="queue-failure-user")
    client = APIClient()
    client.force_authenticate(user=user)
    conversation = client.post("/api/v1/chat/conversations/", {}, format="json").json()

    def fail_to_queue(*, args: list[str], task_id: str) -> None:
        del args, task_id
        raise ConnectionError("broker unavailable")

    monkeypatch.setattr(execute_agent_run_task, "apply_async", fail_to_queue)
    response = client.post(
        "/api/v1/chat/messages/",
        {"conversation_id": conversation["id"], "message": "hello"},
        format="json",
    )

    assert response.status_code == 503
    run = AgentRun.objects.get()
    assert run.status == "pending"
    assert run.execution_task_id == ""


@pytest.mark.django_db
def test_celery_task_executes_the_reserved_run(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.conversations.models import Conversation
    from apps.conversations.services import StartRunCommand

    user = User.objects.create_user(username="worker-user")
    run = AgentRunService.start(
        StartRunCommand(
            conversation=Conversation.objects.create(user=user),
            operation_id=uuid4(),
            request_id="worker-request",
            message="hello",
        )
    )
    expected_task_id = str(uuid4())
    assert AgentRunService.reserve_execution_task(run, expected_task_id)

    def fake_execute(
        selected_run: AgentRun,
        *,
        actor: User,
        task_id: str | None,
    ) -> SimpleNamespace:
        assert selected_run.pk == run.pk
        assert actor == user
        assert task_id == expected_task_id
        return SimpleNamespace(status="completed")

    monkeypatch.setattr("apps.conversations.tasks.execute_agent_run", fake_execute)

    result = execute_agent_run_task.apply(args=[str(run.pk)], task_id=expected_task_id)

    assert result.get() == "completed"


def test_sse_terminal_state_rules() -> None:
    from apps.conversations.views import _event_stream_is_terminal

    assert _event_stream_is_terminal(SimpleNamespace(status="completed")) is True
    assert _event_stream_is_terminal(SimpleNamespace(status="failed")) is True
    assert _event_stream_is_terminal(SimpleNamespace(status="cancelled")) is True
    assert _event_stream_is_terminal(SimpleNamespace(status="pending")) is False


def test_sse_stays_open_only_while_approved_run_has_reserved_resume() -> None:
    from apps.conversations.views import _event_stream_is_terminal

    reserved = SimpleNamespace(status="waiting_approval", execution_task_id="resume-task")
    unreserved = SimpleNamespace(status="waiting_approval", execution_task_id="")

    assert _event_stream_is_terminal(reserved) is False
    assert _event_stream_is_terminal(unreserved) is True


@pytest.mark.django_db
def test_cancel_is_idempotent_but_rejects_finished_run() -> None:
    user = User.objects.create_user(username="cancel-user")
    client = APIClient()
    client.force_authenticate(user=user)
    conversation = client.post("/api/v1/chat/conversations/", {}, format="json").json()
    from apps.conversations.models import Conversation
    from apps.conversations.services import StartRunCommand

    run = AgentRunService.start(
        StartRunCommand(
            conversation=Conversation.objects.get(pk=conversation["id"]),
            operation_id=uuid4(),
            request_id="cancel-1",
            message="stop",
        )
    )
    response = client.post(f"/api/v1/chat/runs/{run.pk}/cancel/")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert client.post(f"/api/v1/chat/runs/{run.pk}/cancel/").status_code == 200

    finished = AgentRunService.start(
        StartRunCommand(
            conversation=run.conversation,
            operation_id=uuid4(),
            request_id="done-1",
            message="done",
        )
    )
    finished = AgentRunService.mark_running(finished)
    finished = AgentRunService.complete(finished, "done")
    assert client.post(f"/api/v1/chat/runs/{finished.pk}/cancel/").status_code == 409
