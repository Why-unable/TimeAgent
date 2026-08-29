from uuid import UUID

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.planning.automation import AutomationPolicyService
from apps.planning.automation_serializers import (
    AutomationPolicySerializer,
    AutomationPolicyWriteSerializer,
)
from apps.planning.models import AutomationPolicy


class AutomationPolicyListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=AutomationPolicySerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response(
            AutomationPolicySerializer(
                AutomationPolicyService.list(user=_user(request)), many=True
            ).data
        )

    @extend_schema(request=AutomationPolicyWriteSerializer, responses=AutomationPolicySerializer)
    def post(self, request: Request) -> Response:
        serializer = AutomationPolicyWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            policy = AutomationPolicyService.create_or_update(
                user=_user(request), **serializer.validated_data
            )
        except (ValidationError, ValueError) as exc:
            detail = exc.message_dict if isinstance(exc, ValidationError) else str(exc)
            return Response({"detail": detail}, status=400)
        return Response(AutomationPolicySerializer(policy).data, status=201)


class AutomationPolicyDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=AutomationPolicyWriteSerializer,
        responses=AutomationPolicySerializer,
    )
    def patch(self, request: Request, policy_id: UUID) -> Response:
        serializer = AutomationPolicyWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            policy = AutomationPolicyService.update(
                user=_user(request),
                policy_id=policy_id,
                changes=serializer.validated_data,
            )
        except AutomationPolicy.DoesNotExist as exc:
            raise Http404 from exc
        except (ValidationError, ValueError) as exc:
            detail = exc.message_dict if isinstance(exc, ValidationError) else str(exc)
            return Response({"detail": detail}, status=400)
        return Response(AutomationPolicySerializer(policy).data)


def _user(request: Request) -> User:
    if not isinstance(request.user, User):
        raise Http404
    return request.user
