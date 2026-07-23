from datetime import datetime
from typing import Any
from uuid import UUID

from django.conf import settings
from django.contrib.auth.models import User
from django.http import Http404
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications.models import NotificationDelivery, WebPushSubscription
from apps.notifications.selectors import NotificationDeliveryQuery, list_deliveries
from apps.notifications.serializers import (
    NotificationDeliverySerializer,
    NotificationPreferenceSerializer,
    WebPushConfigSerializer,
    WebPushSubscriptionCreateSerializer,
    WebPushSubscriptionSerializer,
)
from apps.notifications.services import NotificationService


def _user(request: Request) -> User:
    if not isinstance(request.user, User):
        raise Http404
    return request.user


class CurrentNotificationPreferenceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=NotificationPreferenceSerializer)
    def get(self, request: Request) -> Response:
        preference = NotificationService.get_or_create_preference(_user(request))
        return Response(NotificationPreferenceSerializer(preference).data)

    @extend_schema(
        request=NotificationPreferenceSerializer, responses=NotificationPreferenceSerializer
    )
    def patch(self, request: Request) -> Response:
        preference = NotificationService.get_or_create_preference(_user(request))
        serializer = NotificationPreferenceSerializer(preference, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = NotificationService.update_preference(_user(request), serializer.validated_data)
        return Response(NotificationPreferenceSerializer(updated).data)


class NotificationDeliveryListView(generics.ListAPIView[NotificationDelivery]):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationDeliverySerializer

    def get_queryset(self) -> Any:
        created_after: datetime | None = None
        raw_created = self.request.query_params.get("created_at")
        if raw_created:
            created_after = parse_datetime(raw_created)
        return list_deliveries(
            NotificationDeliveryQuery(
                user=_user(self.request),
                status=self.request.query_params.get("status"),
                channel_type=self.request.query_params.get("channel_type"),
                source_type=self.request.query_params.get("source_type"),
                created_after=created_after,
            )
        )[:100]


class NotificationDeliveryDetailView(generics.RetrieveAPIView[NotificationDelivery]):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationDeliverySerializer
    lookup_url_kwarg = "delivery_id"

    def get_queryset(self) -> Any:
        return NotificationDelivery.objects.filter(user=_user(self.request))


class WebPushConfigView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=WebPushConfigSerializer)
    def get(self, request: Request) -> Response:
        del request
        public_key = str(getattr(settings, "WEB_PUSH_VAPID_PUBLIC_KEY", "")).strip()
        private_key = str(getattr(settings, "WEB_PUSH_VAPID_PRIVATE_KEY", "")).strip()
        subject = str(getattr(settings, "WEB_PUSH_VAPID_SUBJECT", "")).strip()
        return Response(
            {"configured": bool(public_key and private_key and subject), "public_key": public_key}
        )


class WebPushSubscriptionListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=WebPushSubscriptionSerializer(many=True))
    def get(self, request: Request) -> Response:
        items = WebPushSubscription.objects.filter(user=_user(request))
        return Response(WebPushSubscriptionSerializer(items, many=True).data)

    @extend_schema(
        request=WebPushSubscriptionCreateSerializer,
        responses={status.HTTP_201_CREATED: WebPushSubscriptionSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = WebPushSubscriptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item = NotificationService.save_push_subscription(
                user=_user(request),
                endpoint=str(serializer.validated_data["endpoint"]),
                p256dh=str(serializer.validated_data["p256dh"]),
                auth=str(serializer.validated_data["auth"]),
                user_agent=request.headers.get("User-Agent", ""),
            )
        except PermissionError as exc:
            raise ValidationError({"endpoint": "Subscription cannot be claimed"}) from exc
        return Response(WebPushSubscriptionSerializer(item).data, status=status.HTTP_201_CREATED)


class WebPushSubscriptionDestroyView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    def delete(self, request: Request, subscription_id: UUID) -> Response:
        try:
            NotificationService.delete_push_subscription(
                user=_user(request), subscription_id=subscription_id
            )
        except WebPushSubscription.DoesNotExist as exc:
            raise Http404 from exc
        return Response(status=status.HTTP_204_NO_CONTENT)
