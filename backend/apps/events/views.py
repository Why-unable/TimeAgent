from typing import Any
from uuid import UUID

from django.contrib.auth.models import User
from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.events.models import CalendarEvent
from apps.events.serializers import (
    CalendarEventSerializer,
    CreateCalendarEventSerializer,
    EventListQuerySerializer,
    UpdateCalendarEventSerializer,
)
from apps.events.services import EventQuery, EventService, EventVersionConflictError
from common.serializers import ErrorResponseSerializer


class EventVersionQuerySerializer(serializers.Serializer[Any]):
    expected_version = serializers.IntegerField(min_value=1)


class CalendarEventListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[EventListQuerySerializer],
        responses=CalendarEventSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        user = _authenticated_user(request)
        query_serializer = EventListQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        values = query_serializer.validated_data
        events = EventService.list_events(
            EventQuery(
                user=user,
                starts_before=values.get("starts_before"),
                ends_after=values.get("ends_after"),
                statuses=tuple(values.get("status", ())),
            )
        )
        return Response(CalendarEventSerializer(events, many=True).data)

    @extend_schema(
        request=CreateCalendarEventSerializer,
        responses={status.HTTP_201_CREATED: CalendarEventSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = CreateCalendarEventSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        event = serializer.save()
        return Response(
            CalendarEventSerializer(event).data,
            status=status.HTTP_201_CREATED,
        )


class CalendarEventDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=CalendarEventSerializer)
    def get(self, request: Request, event_id: UUID) -> Response:
        event = _get_event(request, event_id)
        return Response(CalendarEventSerializer(event).data)

    @extend_schema(
        parameters=[EventVersionQuerySerializer],
        request=UpdateCalendarEventSerializer,
        responses={
            status.HTTP_200_OK: CalendarEventSerializer,
            status.HTTP_409_CONFLICT: ErrorResponseSerializer,
        },
    )
    def patch(self, request: Request, event_id: UUID) -> Response:
        event = _get_event(request, event_id)
        query_serializer = EventVersionQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        serializer = UpdateCalendarEventSerializer(
            event,
            data=request.data,
            context={
                "request": request,
                "expected_version": query_serializer.validated_data["expected_version"],
            },
        )
        serializer.is_valid(raise_exception=True)
        try:
            event = serializer.save()
        except EventVersionConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(CalendarEventSerializer(event).data)

    @extend_schema(
        parameters=[EventVersionQuerySerializer],
        request=None,
        responses={
            status.HTTP_204_NO_CONTENT: None,
            status.HTTP_409_CONFLICT: ErrorResponseSerializer,
        },
    )
    def delete(self, request: Request, event_id: UUID) -> Response:
        user = _authenticated_user(request)
        query_serializer = EventVersionQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        try:
            EventService.cancel_event(
                event_id=event_id,
                user=user,
                expected_version=query_serializer.validated_data["expected_version"],
            )
        except CalendarEvent.DoesNotExist as exc:
            raise Http404 from exc
        except EventVersionConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _get_event(request: Request, event_id: UUID) -> CalendarEvent:
    user = _authenticated_user(request)
    try:
        return CalendarEvent.objects.get(pk=event_id, user=user)
    except CalendarEvent.DoesNotExist as exc:
        raise Http404 from exc


def _authenticated_user(request: Request) -> User:
    if not isinstance(request.user, User):
        raise Http404
    return request.user
