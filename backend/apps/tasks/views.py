from uuid import UUID

from django.contrib.auth.models import User
from django.http import Http404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tasks.execution_services import (
    ExecutionSignalIdempotencyConflictError,
    RecordExecutionSignalCommand,
    TaskExecutionSignalService,
)
from apps.tasks.models import InvalidTaskTransitionError, Task
from apps.tasks.serializers import (
    CreateTaskExecutionSignalSerializer,
    CreateTaskSerializer,
    TaskExecutionSignalSerializer,
    TaskExecutionSummarySerializer,
    TaskListQuerySerializer,
    TaskSerializer,
    UpdateTaskSerializer,
)
from apps.tasks.services import TaskQuery, TaskService
from common.serializers import ErrorResponseSerializer


class TaskListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[TaskListQuerySerializer],
        responses=TaskSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        user = _authenticated_user(request)
        query_serializer = TaskListQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        values = query_serializer.validated_data
        tasks = TaskService.list_tasks(
            TaskQuery(
                user=user,
                statuses=tuple(values.get("status", ())),
                due_before=values.get("due_before"),
                planned_starts_before=values.get("planned_starts_before"),
                planned_ends_after=values.get("planned_ends_after"),
            )
        )
        return Response(TaskSerializer(tasks, many=True).data)

    @extend_schema(
        request=CreateTaskSerializer,
        responses={status.HTTP_201_CREATED: TaskSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = CreateTaskSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        task = serializer.save()
        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)


class TaskDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=TaskSerializer)
    def get(self, request: Request, task_id: UUID) -> Response:
        task = _get_task(request, task_id)
        return Response(TaskSerializer(task).data)

    @extend_schema(request=UpdateTaskSerializer, responses=TaskSerializer)
    def patch(self, request: Request, task_id: UUID) -> Response:
        task = _get_task(request, task_id)
        serializer = UpdateTaskSerializer(
            task,
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        task = serializer.save()
        return Response(TaskSerializer(task).data)


class CompleteTaskView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={
            status.HTTP_200_OK: TaskSerializer,
            status.HTTP_409_CONFLICT: ErrorResponseSerializer,
        },
    )
    def post(self, request: Request, task_id: UUID) -> Response:
        user = _authenticated_user(request)
        try:
            current_task = _get_task(request, task_id)
            signal = TaskExecutionSignalService.record(
                RecordExecutionSignalCommand(
                    user=user,
                    task_id=task_id,
                    signal_type="completed",
                    occurred_at=current_task.completed_at or timezone.now(),
                    idempotency_key=f"complete-endpoint:{task_id}",
                    source="web",
                )
            )
            task = signal.task
            task.refresh_from_db()
        except Task.DoesNotExist as exc:
            raise Http404 from exc
        except (InvalidTaskTransitionError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(TaskSerializer(task).data)


class TaskExecutionSignalListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=TaskExecutionSignalSerializer(many=True))
    def get(self, request: Request, task_id: UUID) -> Response:
        user = _authenticated_user(request)
        _get_task(request, task_id)
        signals = TaskExecutionSignalService.list(user=user, task_id=task_id)
        return Response(TaskExecutionSignalSerializer(signals, many=True).data)

    @extend_schema(
        request=CreateTaskExecutionSignalSerializer,
        responses={
            status.HTTP_200_OK: TaskExecutionSignalSerializer,
            status.HTTP_409_CONFLICT: ErrorResponseSerializer,
        },
    )
    def post(self, request: Request, task_id: UUID) -> Response:
        user = _authenticated_user(request)
        _get_task(request, task_id)
        serializer = CreateTaskExecutionSignalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            signal = TaskExecutionSignalService.record(
                RecordExecutionSignalCommand(
                    user=user,
                    task_id=task_id,
                    **serializer.validated_data,
                )
            )
        except ExecutionSignalIdempotencyConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except (InvalidTaskTransitionError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(
            TaskExecutionSignalSerializer(signal).data,
            status=status.HTTP_200_OK,
        )


class TaskExecutionSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=TaskExecutionSummarySerializer)
    def get(self, request: Request, task_id: UUID) -> Response:
        user = _authenticated_user(request)
        _get_task(request, task_id)
        summary = TaskExecutionSignalService.summary(
            user=user,
            task_id=task_id,
            now=timezone.now(),
        )
        payload = {
            "task_id": summary.task_id,
            "signal_count": summary.signal_count,
            "active_seconds": summary.active_seconds,
            "planned_seconds": summary.planned_seconds,
            "estimated_seconds": summary.estimated_seconds,
            "variance_vs_plan_seconds": summary.variance_vs_plan_seconds,
            "variance_vs_estimate_seconds": summary.variance_vs_estimate_seconds,
            "evidence_status": summary.evidence_status,
            "open_started_at": summary.open_started_at,
            "last_signal_type": summary.last_signal_type,
        }
        return Response(TaskExecutionSummarySerializer(payload).data)


def _get_task(request: Request, task_id: UUID) -> Task:
    user = _authenticated_user(request)
    try:
        return Task.objects.get(pk=task_id, user=user)
    except Task.DoesNotExist as exc:
        raise Http404 from exc


def _authenticated_user(request: Request) -> User:
    if not isinstance(request.user, User):
        raise Http404
    return request.user
