from uuid import UUID

from django.contrib.auth.models import User
from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.memory.store import open_postgres_store
from apps.planning.models import SchedulePlan
from apps.planning.serializers import (
    SchedulePlanApplySerializer,
    SchedulePlanCompareSerializer,
    SchedulePlanComparisonSerializer,
    SchedulePlanCreateSerializer,
    SchedulePlanEditSerializer,
    SchedulePlanRegenerateSerializer,
    SchedulePlanSerializer,
    SchedulePlanValidationResultSerializer,
    SchedulePlanValidationSerializer,
)
from apps.planning.services import PlanningService
from apps.time_memory.decision_profile import DecisionProfileService


class SchedulePlanListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=SchedulePlanCreateSerializer, responses=SchedulePlanSerializer)
    def post(self, request: Request) -> Response:
        user = _authenticated_user(request)
        serializer = SchedulePlanCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            plan = PlanningService.propose_schedule_plan(
                user=user,
                task_ids=data["task_ids"],
                range_start=data["range_start"],
                range_end=data["range_end"],
                strategy=data["strategy"],
                ordering=data["ordering"],
                decision_profile_snapshot=_decision_profile_snapshot(user),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SchedulePlanSerializer(plan).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=SchedulePlanSerializer(many=True))
    def get(self, request: Request) -> Response:
        user = _authenticated_user(request)
        plans = PlanningService.list_schedule_plans(user=user)
        return Response(SchedulePlanSerializer(plans, many=True).data)


class SchedulePlanApplyView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=SchedulePlanApplySerializer, responses=SchedulePlanSerializer)
    def post(self, request: Request, plan_id: UUID) -> Response:
        user = _authenticated_user(request)
        serializer = SchedulePlanApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            plan = PlanningService.apply_schedule_plan(
                user=user,
                plan_id=plan_id,
                expected_version=serializer.validated_data["expected_version"],
            )
        except SchedulePlan.DoesNotExist:
            raise Http404 from None
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(SchedulePlanSerializer(plan).data)


class SchedulePlanCompareView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=SchedulePlanCompareSerializer,
        responses=SchedulePlanComparisonSerializer,
    )
    def post(self, request: Request) -> Response:
        user = _authenticated_user(request)
        serializer = SchedulePlanCompareSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = PlanningService.compare_schedule_plans(
                user=user,
                decision_profile_snapshot=_decision_profile_snapshot(user),
                **serializer.validated_data,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "alternatives": SchedulePlanSerializer(result.alternatives, many=True).data,
                "comparison": result.comparison,
                "claim": result.claim,
            },
            status=status.HTTP_201_CREATED,
        )


class SchedulePlanRegenerateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=SchedulePlanRegenerateSerializer, responses=SchedulePlanSerializer)
    def post(self, request: Request, plan_id: UUID) -> Response:
        user = _authenticated_user(request)
        serializer = SchedulePlanRegenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            plan = PlanningService.regenerate_schedule_plan(
                user=user, plan_id=plan_id, **serializer.validated_data
            )
        except SchedulePlan.DoesNotExist:
            raise Http404 from None
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(SchedulePlanSerializer(plan).data)


class SchedulePlanEditView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=SchedulePlanEditSerializer, responses=SchedulePlanSerializer)
    def post(self, request: Request, plan_id: UUID) -> Response:
        user = _authenticated_user(request)
        serializer = SchedulePlanEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            plan = PlanningService.edit_schedule_plan(
                user=user,
                plan_id=plan_id,
                expected_version=serializer.validated_data["expected_version"],
                edits=serializer.validated_data["items"],
            )
        except SchedulePlan.DoesNotExist:
            raise Http404 from None
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(SchedulePlanSerializer(plan).data)


class SchedulePlanValidateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=SchedulePlanValidationSerializer,
        responses=SchedulePlanValidationResultSerializer,
    )
    def post(self, request: Request, plan_id: UUID) -> Response:
        user = _authenticated_user(request)
        serializer = SchedulePlanValidationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = PlanningService.validate_schedule_plan(
                user=user,
                plan_id=plan_id,
                expected_version=serializer.validated_data["expected_version"],
            )
        except SchedulePlan.DoesNotExist:
            raise Http404 from None
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(
            {
                "plan": SchedulePlanSerializer(result.plan).data,
                "valid": result.is_valid,
                "reason_codes": result.reason_codes,
                "checked_at": result.checked_at,
            }
        )


class SchedulePlanAbandonView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=SchedulePlanApplySerializer, responses=SchedulePlanSerializer)
    def post(self, request: Request, plan_id: UUID) -> Response:
        user = _authenticated_user(request)
        serializer = SchedulePlanApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            plan = PlanningService.abandon_schedule_plan(
                user=user,
                plan_id=plan_id,
                expected_version=serializer.validated_data["expected_version"],
            )
        except SchedulePlan.DoesNotExist:
            raise Http404 from None
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(SchedulePlanSerializer(plan).data)


def _authenticated_user(request: Request) -> User:
    if not isinstance(request.user, User):
        raise Http404
    return request.user


def _decision_profile_snapshot(user: User) -> dict[str, object]:
    with open_postgres_store() as store:
        return DecisionProfileService.get(user=user, store=store).as_dict()
