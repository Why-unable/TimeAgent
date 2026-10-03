from uuid import UUID

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.interactions.serializers import (
    EnsureInteractionSerializer,
    InteractionArtifactSerializer,
    InteractionSubmissionResponseSerializer,
    InteractionSubmitSerializer,
    InteractionTelemetrySerializer,
)
from apps.interactions.services import (
    InteractionArtifactService,
    InteractionConflictError,
    InteractionTelemetryService,
)
from apps.planning.serializers import SchedulePlanSerializer


class InteractionListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=InteractionArtifactSerializer(many=True))
    def get(self, request: Request) -> Response:
        user = _authenticated_user(request)
        try:
            plan_id = (
                UUID(request.query_params["plan_id"])
                if request.query_params.get("plan_id")
                else None
            )
            task_id = (
                UUID(request.query_params["task_id"])
                if request.query_params.get("task_id")
                else None
            )
        except ValueError:
            return Response(
                {"detail": "Invalid plan_id or task_id"}, status=status.HTTP_400_BAD_REQUEST
            )
        interaction_type = request.query_params.get("type")
        rows = InteractionArtifactService.list_pending(
            user=user, plan_id=plan_id, task_id=task_id, interaction_type=interaction_type
        )
        return Response(InteractionArtifactSerializer(rows, many=True).data)

    @extend_schema(request=EnsureInteractionSerializer, responses=InteractionArtifactSerializer)
    def post(self, request: Request) -> Response:
        user = _authenticated_user(request)
        serializer = EnsureInteractionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            artifact = InteractionArtifactService.ensure(user=user, **serializer.validated_data)
        except ObjectDoesNotExist:
            raise Http404 from None
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(InteractionArtifactSerializer(artifact).data, status=status.HTTP_200_OK)


class InteractionSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=InteractionSubmitSerializer,
        responses={status.HTTP_200_OK: InteractionSubmissionResponseSerializer},
    )
    def post(self, request: Request, interaction_id: UUID) -> Response:
        user = _authenticated_user(request)
        serializer = InteractionSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = InteractionArtifactService.submit(
                user=user,
                interaction_id=interaction_id,
                **serializer.validated_data,
            )
        except ObjectDoesNotExist:
            raise Http404 from None
        except InteractionConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        plan = result.plan
        if plan is None and result.interaction.plan_id:
            interaction_plan = result.interaction.plan
            if interaction_plan is not None:
                interaction_plan.refresh_from_db()
                plan = interaction_plan
        return Response(
            {
                "accepted": result.accepted,
                "detail": result.detail,
                "interaction": InteractionArtifactSerializer(result.interaction).data,
                "plan": SchedulePlanSerializer(plan).data if plan is not None else None,
                "reason_codes": list(result.reason_codes),
                "conflicts": list(result.conflicts),
                "candidate": result.candidate,
                "replayed": result.replayed,
            },
            status=status.HTTP_200_OK,
        )


class InteractionTelemetryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=InteractionTelemetrySerializer, responses={202: None})
    def post(self, request: Request) -> Response:
        serializer = InteractionTelemetrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        InteractionTelemetryService.record(event_data=serializer.validated_data)
        return Response(status=status.HTTP_202_ACCEPTED)


def _authenticated_user(request: Request) -> User:
    if not isinstance(request.user, User):
        raise Http404
    return request.user
