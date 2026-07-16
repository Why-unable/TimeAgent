from typing import cast

from django.contrib.auth.models import AbstractBaseUser
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.preferences.serializers import UserPreferenceSerializer
from apps.preferences.services import UserPreferenceService


class CurrentUserPreferenceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserPreferenceSerializer)
    def get(self, request: Request) -> Response:
        user = cast(AbstractBaseUser, request.user)
        preference = UserPreferenceService.get_or_create_for_user(user)
        return Response(UserPreferenceSerializer(preference).data)

    @extend_schema(
        request=UserPreferenceSerializer,
        responses=UserPreferenceSerializer,
    )
    def patch(self, request: Request) -> Response:
        user = cast(AbstractBaseUser, request.user)
        preference = UserPreferenceService.get_or_create_for_user(user)
        serializer = UserPreferenceSerializer(preference, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        preference = UserPreferenceService.update_for_user(user, serializer.validated_data)
        return Response(UserPreferenceSerializer(preference).data)
