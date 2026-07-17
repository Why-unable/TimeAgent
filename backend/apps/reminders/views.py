from typing import Any
from uuid import UUID

from django.contrib.auth.models import User
from django.http import Http404
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.reminders.models import Reminder
from apps.reminders.serializers import (
    CreateReminderSerializer,
    ReminderSerializer,
)
from apps.reminders.services import ReminderCannotCancelError, ReminderService


class ReminderListCreateView(generics.ListCreateAPIView[Reminder]):
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> Any:
        user = self.request.user
        if not isinstance(user, User):
            return Reminder.objects.none()
        return Reminder.objects.filter(user=user).order_by("trigger_at", "id")

    def get_serializer_class(self) -> Any:
        if self.request.method == "POST":
            return CreateReminderSerializer
        return ReminderSerializer

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        input_serializer = self.get_serializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        reminder = input_serializer.save()
        output_serializer = ReminderSerializer(reminder, context=self.get_serializer_context())
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=CreateReminderSerializer(),
        responses={status.HTTP_201_CREATED: ReminderSerializer()},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().post(request, *args, **kwargs)


class ReminderDestroyView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={
            status.HTTP_204_NO_CONTENT: None,
            status.HTTP_409_CONFLICT: OpenApiResponse(
                description="Reminder can no longer be cancelled"
            ),
        },
    )
    def delete(self, request: Request, reminder_id: UUID) -> Response:
        if not isinstance(request.user, User):
            raise Http404
        try:
            ReminderService.cancel_reminder(
                reminder_id=reminder_id,
                user=request.user,
                occurred_at=timezone.now(),
            )
        except Reminder.DoesNotExist as exc:
            raise Http404 from exc
        except ReminderCannotCancelError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
