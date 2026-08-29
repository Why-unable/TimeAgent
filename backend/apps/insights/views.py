from uuid import UUID

from django.contrib.auth.models import User
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.insights.serializers import TemporalInsightActionSerializer, TemporalInsightSerializer
from apps.insights.services import TemporalInsightService


class TemporalInsightListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=TemporalInsightSerializer(many=True))
    def get(self, request: Request) -> Response:
        user = request.user
        if not isinstance(user, User):
            return Response([], status=401)
        TemporalInsightService.scan(user=user)
        return Response(
            TemporalInsightSerializer(TemporalInsightService.list_open(user=user), many=True).data
        )


class TemporalInsightActionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=TemporalInsightActionSerializer, responses=TemporalInsightSerializer)
    def post(self, request: Request, insight_id: UUID) -> Response:
        serializer = TemporalInsightActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not isinstance(user, User):
            return Response({"detail": "Authentication required"}, status=401)
        insight = TemporalInsightService.act(
            user=user, insight_id=insight_id, **serializer.validated_data
        )
        return Response(TemporalInsightSerializer(insight).data)


class TemporalInsightDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=TemporalInsightSerializer)
    def get(self, request: Request, insight_id: UUID) -> Response:
        user = request.user
        if not isinstance(user, User):
            return Response({"detail": "Authentication required"}, status=401)
        insight = TemporalInsightService.get(user=user, insight_id=insight_id)
        return Response(TemporalInsightSerializer(insight).data)
