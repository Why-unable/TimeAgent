from dataclasses import asdict

from django.contrib.auth.models import User
from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.planning.adaptive import AdaptivePlanningService
from apps.planning.adaptive_serializers import (
    DisruptionDetectionRequestSerializer,
    LocalReplanApplyRequestSerializer,
    LocalReplanPreviewRequestSerializer,
    LocalReplanPreviewSerializer,
    ScheduleDisruptionSerializer,
)
from apps.planning.automation import AutomationPolicyService
from apps.planning.change_serializers import ScheduleChangeBatchSerializer
from apps.planning.models import AutomationPolicy


class LocalReplanPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=LocalReplanPreviewRequestSerializer,
        responses=LocalReplanPreviewSerializer,
    )
    def post(self, request: Request) -> Response:
        if not isinstance(request.user, User):
            raise Http404
        serializer = LocalReplanPreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            preview = AdaptivePlanningService.preview_local_replan(
                user=request.user,
                blocked_start=data["blocked_start"],
                blocked_end=data["blocked_end"],
                movable_task_ids=data["movable_task_ids"],
                horizon_end=data["horizon_end"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            LocalReplanPreviewSerializer(
                {
                    "blocked_start": preview.blocked_start,
                    "blocked_end": preview.blocked_end,
                    "moved_items": preview.moved_items,
                    "unchanged_task_ids": preview.unchanged_task_ids,
                    "stability_cost": preview.stability_cost,
                    "reason": preview.reason,
                }
            ).data
        )


class ScheduleDisruptionDetectionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=DisruptionDetectionRequestSerializer,
        responses=ScheduleDisruptionSerializer(many=True),
    )
    def post(self, request: Request) -> Response:
        if not isinstance(request.user, User):
            raise Http404
        serializer = DisruptionDetectionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            disruptions = AdaptivePlanningService.detect_disruptions(
                user=request.user,
                **serializer.validated_data,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        response_data = [asdict(item) for item in disruptions]
        result = ScheduleDisruptionSerializer(response_data, many=True)  # type: ignore[arg-type]
        return Response(result.data)


class LocalReplanApplyView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=LocalReplanApplyRequestSerializer,
        responses={200: ScheduleChangeBatchSerializer, 201: ScheduleChangeBatchSerializer},
    )
    def post(self, request: Request) -> Response:
        if not isinstance(request.user, User):
            raise Http404
        serializer = LocalReplanApplyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        existing = AdaptivePlanningService.find_change_batch(
            user=request.user, operation_id=data["operation_id"]
        )
        if existing is not None:
            return Response(ScheduleChangeBatchSerializer(existing).data)
        try:
            policy = AutomationPolicyService.get(
                policy_id=data["policy_id"], user=request.user
            )
        except AutomationPolicy.DoesNotExist as exc:
            raise Http404 from exc
        if policy.requires_approval:
            return Response(
                {"detail": "This automation policy requires HITL approval"},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            preview = AdaptivePlanningService.preview_local_replan(
                user=request.user,
                blocked_start=data["blocked_start"],
                blocked_end=data["blocked_end"],
                movable_task_ids=data["movable_task_ids"],
                horizon_end=data["horizon_end"],
            )
            batch = AdaptivePlanningService.apply_local_replan(
                user=request.user,
                policy=policy,
                preview=preview,
                operation_id=data["operation_id"],
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(
            ScheduleChangeBatchSerializer(batch).data,
            status=status.HTTP_201_CREATED,
        )
