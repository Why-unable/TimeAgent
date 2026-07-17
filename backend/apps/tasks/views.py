from uuid import UUID

from django.contrib.auth.models import User
from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tasks.models import InvalidTaskTransitionError, Task
from apps.tasks.serializers import (
    CreateTaskSerializer,
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
            task = TaskService.complete_task(task_id=task_id, user=user)
        except Task.DoesNotExist as exc:
            raise Http404 from exc
        except InvalidTaskTransitionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(TaskSerializer(task).data)


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
