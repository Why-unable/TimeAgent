from uuid import UUID

from django.contrib.auth.models import User
from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.planning.adaptive import AdaptivePlanningService
from apps.planning.change_serializers import ScheduleChangeBatchSerializer
from apps.planning.models import ScheduleChangeBatch


class ScheduleChangeBatchRevertView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ScheduleChangeBatchSerializer

    @extend_schema(responses=ScheduleChangeBatchSerializer)
    def post(self, request: Request, batch_id: UUID) -> Response:
        if not isinstance(request.user, User):
            raise Http404
        try:
            batch = AdaptivePlanningService.revert_batch(user=request.user, batch_id=batch_id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except ScheduleChangeBatch.DoesNotExist:
            raise Http404 from None
        return Response(ScheduleChangeBatchSerializer(batch).data)
