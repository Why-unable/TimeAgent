from django.contrib.auth.models import User
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.planning.recommendation_serializers import (
    FreeTimeRecommendationQuerySerializer,
    FreeTimeRecommendationSerializer,
)
from apps.planning.recommendations import FreeTimeRecommendationService


class FreeTimeRecommendationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[FreeTimeRecommendationQuerySerializer],
        responses=FreeTimeRecommendationSerializer,
    )
    def get(self, request: Request) -> Response:
        serializer = FreeTimeRecommendationQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not isinstance(user, User):
            return Response({"detail": "Authentication required"}, status=401)
        result = FreeTimeRecommendationService.recommend(user=user, **serializer.validated_data)
        return Response(FreeTimeRecommendationSerializer(result).data)
