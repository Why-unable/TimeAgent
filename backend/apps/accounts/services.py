from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.authtoken.models import Token

logger = logging.getLogger(__name__)


class AuthenticationFailedError(ValueError):
    pass


class RegistrationDisabledError(ValueError):
    pass


class PasswordResetTokenError(ValueError):
    pass


class EmailVerificationTokenError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PasswordResetRequest:
    email: str
    application_url: str


@dataclass(frozen=True, slots=True)
class EmailVerificationRequest:
    email: str
    application_url: str


class AccountService:
    @staticmethod
    @transaction.atomic
    def register(*, email: str, nickname: str, password: str, application_url: str) -> User:
        if not settings.AUTH_REGISTRATION_ENABLED:
            raise RegistrationDisabledError("Registration is disabled")
        normalized_email = AccountService._normalize_email(email)
        normalized_nickname = AccountService._normalize_nickname(nickname)
        user_model = get_user_model()
        candidate = user_model(
            username=normalized_email,
            email=normalized_email,
            first_name=normalized_nickname,
        )
        try:
            validate_password(password, candidate)
        except ValidationError as exc:
            raise ValueError(list(exc.messages)) from exc
        try:
            with transaction.atomic():
                user = user_model.objects.create_user(
                    username=normalized_email,
                    email=normalized_email,
                    first_name=normalized_nickname,
                    password=password,
                    is_active=False,
                )
                AccountService._send_email_verification(user, application_url)
                logger.info("email_verification_requested", extra={"user_id": user.pk})
                return user
        except IntegrityError as exc:
            existing = AccountService._find_user(normalized_email)
            if existing is not None and not existing.is_active:
                AccountService._send_email_verification(existing, application_url)
                return existing
            raise ValueError("An account with this email already exists") from exc

    @staticmethod
    def login(request: HttpRequest, *, identifier: str, password: str) -> User:
        authenticated = AccountService.verify_credentials(
            request, identifier=identifier, password=password
        )
        login(request, authenticated)
        return authenticated

    @staticmethod
    @transaction.atomic
    def verify_email(*, uid: str, token: str) -> User:
        user = AccountService._user_from_uid(uid, EmailVerificationTokenError)
        if user.is_active or not default_token_generator.check_token(user, token):
            raise EmailVerificationTokenError("Email verification link is invalid or expired")
        user.is_active = True
        user.save(update_fields=["is_active"])
        logger.info("email_verified", extra={"user_id": user.pk})
        return user

    @staticmethod
    def request_email_verification(command: EmailVerificationRequest) -> None:
        user = AccountService._find_user(command.email)
        if user is None or user.is_active or not user.has_usable_password():
            return
        AccountService._send_email_verification(user, command.application_url)
        logger.info("email_verification_resent", extra={"user_id": user.pk})

    @staticmethod
    @transaction.atomic
    def update_nickname(*, user: User, nickname: str) -> User:
        user.first_name = AccountService._normalize_nickname(nickname)
        user.save(update_fields=["first_name"])
        logger.info("account_nickname_updated", extra={"user_id": user.pk})
        return user

    @staticmethod
    def verify_credentials(
        request: HttpRequest | None, *, identifier: str, password: str
    ) -> User:
        """Validate credentials without establishing a session.

        Used by the native token endpoint, which must not set a session cookie —
        otherwise SessionAuthentication would keep the caller logged in even
        after the token is revoked.
        """
        candidate = AccountService._find_user(identifier)
        username = candidate.get_username() if candidate is not None else identifier.strip()
        authenticated = authenticate(request, username=username, password=password)
        if not isinstance(authenticated, User):
            raise AuthenticationFailedError("Invalid email or password")
        return authenticated

    @staticmethod
    @transaction.atomic
    def issue_native_token(*, user: User) -> Token:
        """Rotate and return the single native API token for ``user``.

        Rotation prevents a previously copied token from remaining valid after
        the user signs in again. Token persistence stays behind the application
        service boundary; views never write authentication state directly.
        """
        Token.objects.filter(user=user).delete()
        token = Token.objects.create(user=user)
        logger.info("native_auth_token_issued", extra={"user_id": user.pk})
        return token

    @staticmethod
    @transaction.atomic
    def revoke_native_token(*, token: Token) -> None:
        user_id = token.user_id
        token.delete()
        logger.info("native_auth_token_revoked", extra={"user_id": user_id})

    @staticmethod
    def logout(request: HttpRequest) -> None:
        logout(request)

    @staticmethod
    def request_password_reset(command: PasswordResetRequest) -> None:
        user = AccountService._find_user(command.email)
        if user is None or not user.is_active or not user.has_usable_password() or not user.email:
            return
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        query = urlencode({"reset_uid": uid, "reset_token": token})
        reset_url = f"{command.application_url.rstrip('/')}/login?{query}"
        send_mail(
            subject="Reset your Time Agent password",
            message=(
                "Use the following link to reset your Time Agent password. "
                f"The link expires in {settings.PASSWORD_RESET_TIMEOUT // 3600} hours:\n\n"
                f"{reset_url}"
            ),
            from_email=settings.EMAIL_FROM_ADDRESS,
            recipient_list=[user.email],
            fail_silently=False,
        )

    @staticmethod
    @transaction.atomic
    def reset_password(*, uid: str, token: str, password: str) -> None:
        user = AccountService._user_from_uid(uid, PasswordResetTokenError)
        if not default_token_generator.check_token(user, token):
            raise PasswordResetTokenError("Password reset link is invalid or expired")
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise ValueError(list(exc.messages)) from exc
        user.set_password(password)
        user.save(update_fields=["password"])

    @staticmethod
    def _find_user(identifier: str) -> User | None:
        normalized = AccountService._normalize_email(identifier)
        user_model = get_user_model()
        return (
            user_model.objects.filter(username__iexact=normalized).first()
            or user_model.objects.filter(email__iexact=normalized).first()
        )

    @staticmethod
    def _normalize_email(value: str) -> str:
        return value.strip().casefold()

    @staticmethod
    def _normalize_nickname(value: str) -> str:
        nickname = value.strip()
        if not nickname:
            raise ValueError("Nickname cannot be empty")
        return nickname

    @staticmethod
    def _user_from_uid(uid: str, exception_type: type[ValueError]) -> User:
        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            return get_user_model().objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist) as exc:
            raise exception_type("Verification link is invalid or expired") from exc

    @staticmethod
    def _send_email_verification(user: User, application_url: str) -> None:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        query = urlencode({"verify_uid": uid, "verify_token": token})
        verification_url = f"{application_url.rstrip('/')}/login?{query}"
        send_mail(
            subject="Verify your Time Agent email address",
            message=(
                "Welcome to Time Agent. Verify your email address to activate your account. "
                f"This link expires in {settings.PASSWORD_RESET_TIMEOUT // 3600} hours:\n\n"
                f"{verification_url}"
            ),
            from_email=settings.EMAIL_FROM_ADDRESS,
            recipient_list=[user.email],
            fail_silently=False,
        )
