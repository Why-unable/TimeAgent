from __future__ import annotations

from typing import cast

from django.contrib.auth.models import User
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import (
    AuthTokenSerializer,
    CurrentUserSerializer,
    EmailVerificationConfirmSerializer,
    EmailVerificationRequestSerializer,
    LoginSerializer,
    NicknameUpdateSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
)
from apps.accounts.services import (
    AccountService,
    AuthenticationFailedError,
    EmailVerificationRequest,
    EmailVerificationTokenError,
    GuestAccessDisabledError,
    PasswordResetRequest,
    PasswordResetTokenError,
    RegistrationDisabledError,
)
from apps.accounts.throttles import AuthenticationThrottle, GuestAuthenticationThrottle


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

    @extend_schema(
        request=RegisterSerializer,
        responses={202: OpenApiResponse(description="Verification email sent")},
    )
    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            AccountService.register(
                **serializer.validated_data,
                application_url=request.build_absolute_uri("/"),
            )
        except RegistrationDisabledError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return Response({"detail": exc.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"detail": "Verification email sent"},
            status=status.HTTP_202_ACCEPTED,
        )


class NativeRegisterView(APIView):
    """Stateless registration endpoint for Capacitor's token-auth channel."""

    permission_classes = [AllowAny]
    authentication_classes: list[type] = []
    throttle_classes = [AuthenticationThrottle]
    post = RegisterView.post


@method_decorator(csrf_protect, name="dispatch")
class GuestSessionView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []
    throttle_classes = [GuestAuthenticationThrottle]

    @extend_schema(request=None, responses={200: CurrentUserSerializer})
    def post(self, request: Request) -> Response:
        try:
            user = AccountService.start_guest_session(request._request)
        except GuestAccessDisabledError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response(CurrentUserSerializer(user).data)


class NativeGuestTokenView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []
    throttle_classes = [GuestAuthenticationThrottle]

    @extend_schema(request=None, responses={200: AuthTokenSerializer})
    def post(self, request: Request) -> Response:
        del request
        try:
            user = AccountService.create_guest()
        except GuestAccessDisabledError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        token = AccountService.issue_native_token(user=user)
        return Response(AuthTokenSerializer({"token": token.key, "user": user}).data)


class EmailVerificationConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthenticationThrottle]

    @extend_schema(request=EmailVerificationConfirmSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        serializer = EmailVerificationConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            AccountService.verify_email(**serializer.validated_data)
        except EmailVerificationTokenError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmailVerificationRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthenticationThrottle]

    @extend_schema(request=EmailVerificationRequestSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        serializer = EmailVerificationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        AccountService.request_email_verification(
            EmailVerificationRequest(
                email=serializer.validated_data["email"],
                application_url=request.build_absolute_uri("/"),
            )
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


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


class AccountProfileView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=NicknameUpdateSerializer, responses=CurrentUserSerializer)
    def patch(self, request: Request) -> Response:
        serializer = NicknameUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = AccountService.update_nickname(
                user=cast(User, request.user), nickname=serializer.validated_data["nickname"]
            )
        except ValueError as exc:
            return Response({"detail": exc.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CurrentUserSerializer(user).data)


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


class NativePasswordResetRequestView(APIView):
    """Stateless password-reset request endpoint for Capacitor clients."""

    permission_classes = [AllowAny]
    authentication_classes: list[type] = []
    throttle_classes = [AuthenticationThrottle]
    post = PasswordResetRequestView.post


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


class AuthTokenView(APIView):
    """Exchange credentials for a DRF auth token (native app channel).

    Explicitly clears authentication_classes so SessionAuthentication's CSRF
    enforcement does not apply — native clients have no CSRF cookie. Credentials
    are validated exactly as the session LoginView, reusing AccountService.
    """

    permission_classes = [AllowAny]
    authentication_classes: list[type] = []
    throttle_classes = [AuthenticationThrottle]

    @extend_schema(
        request=LoginSerializer,
        responses={200: AuthTokenSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = AccountService.verify_credentials(
                request._request,
                identifier=serializer.validated_data["identifier"],
                password=serializer.validated_data["password"],
            )
        except AuthenticationFailedError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        token = AccountService.issue_native_token(user=user)
        return Response(
            AuthTokenSerializer({"token": token.key, "user": user}).data,
            status=status.HTTP_200_OK,
        )


class AuthTokenRevokeView(APIView):
    """Delete the caller's auth token (native app logout)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        if isinstance(request.auth, Token):
            AccountService.revoke_native_token(token=request.auth)
        return Response(status=status.HTTP_204_NO_CONTENT)
