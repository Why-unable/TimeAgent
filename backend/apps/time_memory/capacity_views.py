from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.http import Http404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.time_memory.capacity import CapacityForecastService
from apps.time_memory.capacity_serializers import CapacityForecastSerializer
from common.time import to_utc


class CapacityForecastView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter("range_start", str, required=False),
            OpenApiParameter("range_end", str, required=False),
        ],
        responses=CapacityForecastSerializer,
    )
    def get(self, request: Request) -> Response:
        if not isinstance(request.user, User):
            raise Http404
        try:
            start_value = request.query_params.get("range_start")
            end_value = request.query_params.get("range_end")
            start = to_utc(datetime.fromisoformat(start_value) if start_value else timezone.now())
            end = to_utc(
                datetime.fromisoformat(end_value) if end_value else start + timedelta(days=7)
            )
            forecast = CapacityForecastService.forecast(
                user=request.user, range_start=start, range_end=end
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(CapacityForecastSerializer(forecast.as_dict()).data)
