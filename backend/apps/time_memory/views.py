from typing import cast
from uuid import UUID

from django.contrib.auth.models import User
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.memory.store import open_postgres_store
from apps.tasks.models import Task
from apps.time_memory.decision_profile import (
    DecisionProfileService,
    RecordDecisionFeedbackCommand,
)
from apps.time_memory.decision_serializers import (
    DecisionFeedbackSerializer,
    DecisionProfileSerializer,
    DurationRecommendationSerializer,
)
from apps.time_memory.management_service import TimeMemoryManagementService
from apps.time_memory.models import TimeMemoryRefreshState
from apps.time_memory.serializers import TimeMemoryStatusSerializer


class CurrentTimeMemoryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=TimeMemoryStatusSerializer)
    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        with open_postgres_store() as store:
            profile = TimeMemoryManagementService.get_profile(user=user, store=store)
        refresh = TimeMemoryRefreshState.objects.filter(user=user).first()
        return Response(
            {
                "profile": profile.model_dump(mode="json") if profile else None,
                "refresh_status": refresh.status if refresh else "clean",
                "dirty_at": refresh.dirty_at if refresh else None,
                "last_completed_at": refresh.last_completed_at if refresh else None,
                "last_error": refresh.last_error if refresh else "",
            }
        )

    @extend_schema(responses={204: None})
    def delete(self, request: Request) -> Response:
        user = cast(User, request.user)
        with open_postgres_store() as store:
            TimeMemoryManagementService.clear_profile(user=user, store=store)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DecisionProfileView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=DecisionProfileSerializer)
    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        with open_postgres_store() as store:
            profile = DecisionProfileService.get(user=user, store=store)
        return Response(profile.as_dict())

    @extend_schema(request=DecisionFeedbackSerializer, responses={201: None, 200: None})
    def post(self, request: Request) -> Response:
        serializer = DecisionFeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = cast(User, request.user)
        try:
            feedback = DecisionProfileService.record_feedback(
                RecordDecisionFeedbackCommand(user=user, **serializer.validated_data)
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response({"id": feedback.pk}, status=status.HTTP_201_CREATED)


class DurationRecommendationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=DurationRecommendationSerializer)
    def get(self, request: Request, task_id: UUID) -> Response:
        user = cast(User, request.user)
        try:
            with open_postgres_store() as store:
                recommendation = DecisionProfileService.recommend_duration(
                    user=user, store=store, task_id=task_id
                )
        except Task.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(recommendation.as_dict())


class TimeMemoryPlaceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={204: None, 404: None})
    def delete(self, request: Request, place_id: str) -> Response:
        user = cast(User, request.user)
        with open_postgres_store() as store:
            removed = TimeMemoryManagementService.exclude_place(
                user=user, store=store, place_id=place_id
            )
        return Response(status=status.HTTP_204_NO_CONTENT if removed else status.HTTP_404_NOT_FOUND)


class TimeMemoryPatternView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={204: None, 404: None})
    def delete(self, request: Request, pattern_id: str) -> Response:
        user = cast(User, request.user)
        with open_postgres_store() as store:
            removed = TimeMemoryManagementService.exclude_pattern(
                user=user, store=store, pattern_id=pattern_id
            )
        return Response(status=status.HTTP_204_NO_CONTENT if removed else status.HTTP_404_NOT_FOUND)
