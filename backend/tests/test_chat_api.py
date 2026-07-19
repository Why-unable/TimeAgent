from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.http import StreamingHttpResponse
from langchain_core.messages import AIMessage, AIMessageChunk
from rest_framework.test import APIClient

from apps.conversations.execution import _last_ai_text, _message_text, _stream_mode_data
from apps.conversations.models import AgentRun, Conversation
from apps.conversations.services import AgentRunService, StartRunCommand
from apps.conversations.tasks import execute_agent_run_task


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


def test_final_ai_message_accepts_content_blocks() -> None:
    assert (
        _last_ai_text(
            {"messages": [AIMessage(content=[{"type": "text", "text": "done"}])]}
        )
        == "done"
    )


def test_empty_final_ai_message_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="empty final AI message"):
        _last_ai_text({"messages": [AIMessage(content="")]})


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
    content = b"".join(stream.streaming_content)
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


@pytest.mark.django_db(transaction=True)
def test_sse_waits_for_events_until_run_reaches_terminal_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.conversations.models import Conversation
    from apps.conversations.services import StartRunCommand
    from apps.conversations.views import _sse

    user = User.objects.create_user(username="stream-user")
    conversation = Conversation.objects.create(user=user)
    run = AgentRunService.start(
        StartRunCommand(
            conversation=conversation,
            operation_id=uuid4(),
            request_id="stream-request",
            message="hello",
        )
    )
    completed = False

    def complete_during_poll(_seconds: float) -> None:
        nonlocal completed
        if not completed:
            running = AgentRunService.mark_running(run)
            AgentRunService.complete(running, "done")
            completed = True

    monkeypatch.setattr("apps.conversations.views.time.sleep", complete_during_poll)

    content = b"".join(_sse(user_id=user.pk, run_id=run.pk, cursor=0))

    assert b"event: agent.started" in content
    assert b"event: message.completed" in content


@pytest.mark.django_db(transaction=True)
def test_sse_stays_open_while_approved_run_waits_for_celery_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.conversations.models import Conversation
    from apps.conversations.services import StartRunCommand
    from apps.conversations.views import _sse

    user = User.objects.create_user(username="resume-stream-user")
    conversation = Conversation.objects.create(user=user)
    run = AgentRunService.start(
        StartRunCommand(
            conversation=conversation,
            operation_id=uuid4(),
            request_id="resume-stream-request",
            message="create an event",
        )
    )
    run = AgentRunService.mark_running(run)
    run = AgentRunService.wait_for_approval(run)
    task_id = "reserved-resume-task"
    assert AgentRunService.reserve_resume_task(run, task_id)
    resumed = False

    def resume_during_poll(_seconds: float) -> None:
        nonlocal resumed
        if resumed:
            return
        claimed = AgentRunService.claim_for_resume(run, task_id=task_id)
        assert claimed is not None
        AgentRunService.complete(claimed, "resumed reply")
        resumed = True

    monkeypatch.setattr("apps.conversations.views.time.sleep", resume_during_poll)

    content = b"".join(_sse(user_id=user.pk, run_id=run.pk, cursor=0))

    assert b"event: agent.resumed" in content
    assert b"event: message.completed" in content
    assert b"resumed reply" in content


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
