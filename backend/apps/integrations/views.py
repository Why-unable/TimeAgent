from uuid import UUID

from django.conf import settings
from django.contrib.auth.models import User
from django.http import Http404, HttpResponseBase
from django.shortcuts import redirect
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.integrations.calendar.exceptions import (
    ExternalCalendarError,
    ExternalCalendarNotConfigured,
)
from apps.integrations.calendar.oauth_services import CalendarOAuthService
from apps.integrations.calendar.providers.registry import build_calendar_provider
from apps.integrations.calendar.sync_services import (
    CalendarSyncService,
    CalendarSyncUnavailableError,
    SyncExternalCalendarCommand,
)
from apps.integrations.models import CalendarSyncConnection
from apps.integrations.serializers import (
    CalendarOAuthCallbackQuerySerializer,
    CalendarOAuthStartResultSerializer,
    CalendarSyncConnectionSerializer,
    CalendarSyncConnectionWriteSerializer,
    CalendarSyncRequestSerializer,
    CalendarSyncResultSerializer,
)


class CalendarSyncConnectionListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=CalendarSyncConnectionSerializer(many=True))
    def get(self, request: Request) -> Response:
        user = _authenticated_user(request)
        connections = CalendarSyncService.list_connections(user=user)
        return Response(CalendarSyncConnectionSerializer(connections, many=True).data)

    @extend_schema(
        request=CalendarSyncConnectionWriteSerializer,
        responses=CalendarSyncConnectionSerializer,
    )
    def post(self, request: Request) -> Response:
        user = _authenticated_user(request)
        serializer = CalendarSyncConnectionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            connection = CalendarSyncService.create_connection(
                user=user,
                provider_name=serializer.validated_data["provider_name"],
                account_reference=serializer.validated_data["account_reference"],
                calendar_id=serializer.validated_data["calendar_id"],
                calendar_name=serializer.validated_data["calendar_name"],
                timezone_name=serializer.validated_data["timezone"],
                enabled=serializer.validated_data["enabled"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(CalendarSyncConnectionSerializer(connection).data, status=201)


class CalendarSyncRunView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=CalendarSyncRequestSerializer,
        responses=CalendarSyncResultSerializer,
    )
    def post(self, request: Request, connection_id: UUID) -> Response:
        user = _authenticated_user(request)
        serializer = CalendarSyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            connection = CalendarSyncService.get_connection(
                user=user,
                connection_id=connection_id,
            )
        except CalendarSyncConnection.DoesNotExist as exc:
            raise Http404 from exc
        try:
            result = CalendarSyncService.sync(
                SyncExternalCalendarCommand(
                    user=user,
                    connection_id=connection.pk,
                    provider=build_calendar_provider(connection),
                    starts_at_or_after=serializer.validated_data["starts_at_or_after"],
                    starts_before=serializer.validated_data["starts_before"],
                )
            )
        except ExternalCalendarNotConfigured as exc:
            CalendarSyncService.record_connection_error(
                user=user,
                connection_id=connection.id,
                error=exc,
            )
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except ExternalCalendarError as exc:
            CalendarSyncService.record_connection_error(
                user=user,
                connection_id=connection.id,
                error=exc,
            )
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except (ValueError, CalendarSyncUnavailableError) as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            {
                "connection_id": str(result.connection_id),
                "fetched_count": result.fetched_count,
                "created_count": result.created_count,
                "updated_count": result.updated_count,
                "cancelled_count": result.cancelled_count,
                "synced_at": result.synced_at.isoformat(),
            }
        )


class GoogleCalendarOAuthStartView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "calendar_oauth"

    @extend_schema(request=None, responses={200: CalendarOAuthStartResultSerializer})
    def post(self, request: Request) -> Response:
        user = _authenticated_user(request)
        try:
            result = CalendarOAuthService.begin_google(user=user)
        except ExternalCalendarNotConfigured as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except ExternalCalendarError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response(
            {
                "authorization_url": result.authorization_url,
                "expires_at": result.expires_at.isoformat(),
            }
        )


class GoogleCalendarOAuthCallbackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(
        parameters=[CalendarOAuthCallbackQuerySerializer],
        responses={302: None},
    )
    def get(self, request: Request) -> HttpResponseBase:
        serializer = CalendarOAuthCallbackQuerySerializer(data=request.query_params)
        if not serializer.is_valid() or "error" in serializer.validated_data:
            raw_state = request.query_params.get("state")
            if raw_state:
                try:
                    CalendarOAuthService.reject_google(state=raw_state)
                except ExternalCalendarError:
                    return redirect(settings.CALENDAR_OAUTH_FAILURE_URL)
            return redirect(settings.CALENDAR_OAUTH_FAILURE_URL)
        try:
            CalendarOAuthService.complete_google(
                state=serializer.validated_data["state"],
                code=serializer.validated_data["code"],
            )
        except ExternalCalendarError:
            return redirect(settings.CALENDAR_OAUTH_FAILURE_URL)
        return redirect(settings.CALENDAR_OAUTH_SUCCESS_URL)


class GoogleCalendarDisconnectView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def delete(self, request: Request, connection_id: UUID) -> Response:
        user = _authenticated_user(request)
        try:
            CalendarOAuthService.disconnect_google_connection(
                user=user,
                connection_id=connection_id,
            )
        except CalendarSyncConnection.DoesNotExist as exc:
            raise Http404 from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


def _authenticated_user(request: Request) -> User:
    if not isinstance(request.user, User):
        raise Http404
    return request.user
