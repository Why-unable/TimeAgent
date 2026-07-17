from django.contrib.auth.models import User
from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.today.serializers import TodaySummarySerializer
from apps.today.services import TodayService


class TodaySummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=TodaySummarySerializer)
    def get(self, request: Request) -> Response:
        user = request.user
        if not isinstance(user, User):
            raise Http404
        summary = TodayService.get_summary(user=user)
        return Response(TodaySummarySerializer(summary).data)
