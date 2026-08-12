from dataclasses import asdict

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.app_updates.serializers import AndroidUpdateResponseSerializer
from apps.app_updates.services import AndroidUpdateService


class AndroidUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=AndroidUpdateResponseSerializer)
    def get(self, request: Request) -> Response:
        del request
        release = AndroidUpdateService.latest_release()
        return Response(
            {"enabled": release is not None, "release": asdict(release) if release else None}
        )
