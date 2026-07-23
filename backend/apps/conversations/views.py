import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

from asgiref.sync import sync_to_async
from django.contrib.auth.models import User
from django.db import close_old_connections
from django.http import Http404, StreamingHttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.conversations.models import AgentRun, AgentRunStatus, Conversation
from apps.conversations.renderers import EventStreamRenderer
from apps.conversations.serializers import (
    AgentRunSerializer,
    ConversationDetailSerializer,
    ConversationSerializer,
    CreateConversationSerializer,
    CreateMessageSerializer,
)
from apps.conversations.services import (
    AgentRunService,
    ConversationService,
    RunCancellationError,
    StartRunCommand,
)
from apps.conversations.tasks import execute_agent_run_task

TERMINAL_RUN_STATUSES = {
    AgentRunStatus.COMPLETED,
    AgentRunStatus.FAILED,
    AgentRunStatus.CANCELLED,
    AgentRunStatus.WAITING_APPROVAL,
}
SSE_POLL_INTERVAL_SECONDS = 0.25
SSE_HEARTBEAT_INTERVAL_SECONDS = 10.0


class AgentQueueUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The agent execution queue is unavailable"
    default_code = "agent_queue_unavailable"


def _user(request: Request) -> User:
    if not isinstance(request.user, User):
        raise Http404
    return request.user


class ConversationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ConversationSerializer(many=True))
    def get(self, request: Request) -> Response:
        conversations = ConversationService.list(user=_user(request))
        return Response(ConversationSerializer(conversations, many=True).data)

    @extend_schema(request=CreateConversationSerializer, responses={201: ConversationSerializer})
    def post(self, request: Request) -> Response:
        serializer = CreateConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversation = ConversationService.create(
            user=_user(request), title=serializer.validated_data["title"]
        )
        return Response(ConversationSerializer(conversation).data, status=status.HTTP_201_CREATED)


class ConversationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ConversationDetailSerializer)
    def get(self, request: Request, conversation_id: UUID) -> Response:
        try:
            conversation = ConversationService.get_with_runs(
                user=_user(request),
                conversation_id=conversation_id,
            )
        except Conversation.DoesNotExist as exc:
            raise Http404 from exc
        return Response(ConversationDetailSerializer(conversation).data)


class ChatMessageView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=CreateMessageSerializer, responses={202: AgentRunSerializer})
    def post(self, request: Request) -> Response:
        serializer = CreateMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        user = _user(request)
        try:
            conversation = ConversationService.get(
                user=user, conversation_id=values["conversation_id"]
            )
        except Conversation.DoesNotExist as exc:
            raise Http404 from exc
        run = AgentRunService.start(
            StartRunCommand(
                conversation=conversation,
                operation_id=values.get("operation_id", uuid4()),
                request_id=request.headers.get("X-Request-ID", str(uuid4())),
                message=values["message"],
            )
        )
        task_id = str(uuid4())
        if AgentRunService.reserve_execution_task(run, task_id):
            try:
                execute_agent_run_task.apply_async(args=[str(run.pk)], task_id=task_id)
            except Exception as exc:
                AgentRunService.release_execution_task(run, task_id)
                raise AgentQueueUnavailable from exc
            run.refresh_from_db()
        return Response(AgentRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)


class AgentRunDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=AgentRunSerializer)
    def get(self, request: Request, run_id: UUID) -> Response:
        try:
            run = AgentRunService.get(user=_user(request), run_id=run_id)
        except AgentRun.DoesNotExist as exc:
            raise Http404 from exc
        return Response(AgentRunSerializer(run).data)


class AgentRunCancelView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: AgentRunSerializer, 409: OpenApiResponse()})
    def post(self, request: Request, run_id: UUID) -> Response:
        try:
            run = AgentRunService.cancel(user=_user(request), run_id=run_id)
        except AgentRun.DoesNotExist as exc:
            raise Http404 from exc
        except RunCancellationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(AgentRunSerializer(run).data)


class AgentRunEventStreamView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [EventStreamRenderer]

    @extend_schema(
        responses={(200, "text/event-stream"): OpenApiResponse(description="SSE stream")}
    )
    def get(self, request: Request, run_id: UUID) -> StreamingHttpResponse:
        raw_cursor = request.headers.get("Last-Event-ID", request.query_params.get("cursor", "0"))
        try:
            cursor = max(0, int(raw_cursor))
        except ValueError:
            return StreamingHttpResponse(
                iter([b'event: error\ndata: {"detail":"Invalid cursor"}\n\n']),
                status=400,
                content_type="text/event-stream",
            )
        user = _user(request)
        if not AgentRun.objects.filter(pk=run_id, conversation__user=user).exists():
            raise Http404
        response = StreamingHttpResponse(
            _sse(user_id=user.pk, run_id=run_id, cursor=cursor),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


async def _sse(*, user_id: int, run_id: UUID, cursor: int) -> AsyncIterator[bytes]:
    """Yield persisted run events without blocking Django's ASGI event loop.

    ``StreamingHttpResponse`` must receive an asynchronous iterator under
    Uvicorn. A synchronous generator is consumed to completion by Django's
    ASGI adapter, which buffers every SSE frame until the run ends.
    """

    current_cursor = cursor
    last_heartbeat = time.monotonic()
    try:
        while True:
            run, events = await sync_to_async(
                _sse_poll,
                thread_sensitive=True,
            )(user_id=user_id, run_id=run_id, cursor=current_cursor)
            for event in events:
                event_data = {
                    **event.payload,
                    "event_created_at": event.created_at.isoformat(),
                }
                data = json.dumps(event_data, ensure_ascii=False, separators=(",", ":"))
                yield (
                    f"id: {event.sequence}\nevent: {event.event_type}\ndata: {data}\n\n".encode()
                )
                current_cursor = event.sequence

            if _event_stream_is_terminal(run):
                return

            now = time.monotonic()
            if now - last_heartbeat >= SSE_HEARTBEAT_INTERVAL_SECONDS:
                yield b": heartbeat\n\n"
                last_heartbeat = now
            await asyncio.sleep(SSE_POLL_INTERVAL_SECONDS)
    finally:
        await sync_to_async(close_old_connections, thread_sensitive=True)()


def _sse_poll(*, user_id: int, run_id: UUID, cursor: int) -> tuple[AgentRun, list[Any]]:
    close_old_connections()
    run = AgentRun.objects.only("status", "execution_task_id").get(
        pk=run_id,
        conversation__user_id=user_id,
    )
    events = list(run.events.filter(sequence__gt=cursor).order_by("sequence"))
    return run, events


def _event_stream_is_terminal(run: AgentRun) -> bool:
    """Keep SSE open while an approved run is reserved for Celery resume."""

    if run.status == AgentRunStatus.WAITING_APPROVAL:
        return not bool(run.execution_task_id)
    return run.status in TERMINAL_RUN_STATUSES
