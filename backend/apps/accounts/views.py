from __future__ import annotations

from typing import cast

from django.contrib.auth.models import User
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import (
    CurrentUserSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
)
from apps.accounts.services import (
    AccountService,
    AuthenticationFailedError,
    PasswordResetRequest,
    PasswordResetTokenError,
    RegistrationDisabledError,
)
from apps.accounts.throttles import AuthenticationThrottle


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfTokenView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses={200: OpenApiResponse(description="CSRF cookie issued")})
    def get(self, request: Request) -> Response:
        return Response({"csrfToken": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthenticationThrottle]

    @extend_schema(request=RegisterSerializer, responses={201: CurrentUserSerializer})
    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = AccountService.register(**serializer.validated_data)
        except RegistrationDisabledError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return Response({"detail": exc.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        AccountService.login(
            request._request,
            identifier=user.username,
            password=serializer.validated_data["password"],
        )
        return Response(CurrentUserSerializer(user).data, status=status.HTTP_201_CREATED)


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthenticationThrottle]

    @extend_schema(request=LoginSerializer, responses={200: CurrentUserSerializer})
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = AccountService.login(
                request._request,
                identifier=serializer.validated_data["identifier"],
                password=serializer.validated_data["password"],
            )
        except AuthenticationFailedError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CurrentUserSerializer(user).data)


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        AccountService.logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=CurrentUserSerializer)
    def get(self, request: Request) -> Response:
        return Response(CurrentUserSerializer(cast(User, request.user)).data)


@method_decorator(csrf_protect, name="dispatch")
class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthenticationThrottle]

    @extend_schema(request=PasswordResetRequestSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        AccountService.request_password_reset(
            PasswordResetRequest(
                email=serializer.validated_data["email"],
                application_url=request.build_absolute_uri("/"),
            )
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_protect, name="dispatch")
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthenticationThrottle]

    @extend_schema(request=PasswordResetConfirmSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            AccountService.reset_password(
                uid=serializer.validated_data["uid"],
                token=serializer.validated_data["token"],
                password=serializer.validated_data["password"],
            )
        except PasswordResetTokenError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as exc:
            return Response({"detail": exc.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)
