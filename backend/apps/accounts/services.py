from __future__ import annotations

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


class AuthenticationFailedError(ValueError):
    pass


class RegistrationDisabledError(ValueError):
    pass


class PasswordResetTokenError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PasswordResetRequest:
    email: str
    application_url: str


class AccountService:
    @staticmethod
    @transaction.atomic
    def register(*, email: str, password: str) -> User:
        if not settings.AUTH_REGISTRATION_ENABLED:
            raise RegistrationDisabledError("Registration is disabled")
        normalized_email = AccountService._normalize_email(email)
        user_model = get_user_model()
        candidate = user_model(username=normalized_email, email=normalized_email)
        try:
            validate_password(password, candidate)
        except ValidationError as exc:
            raise ValueError(list(exc.messages)) from exc
        try:
            with transaction.atomic():
                return user_model.objects.create_user(
                    username=normalized_email,
                    email=normalized_email,
                    password=password,
                )
        except IntegrityError as exc:
            raise ValueError("An account with this email already exists") from exc

    @staticmethod
    def login(request: HttpRequest, *, identifier: str, password: str) -> User:
        candidate = AccountService._find_user(identifier)
        username = candidate.get_username() if candidate is not None else identifier.strip()
        authenticated = authenticate(request, username=username, password=password)
        if not isinstance(authenticated, User):
            raise AuthenticationFailedError("Invalid email or password")
        login(request, authenticated)
        return authenticated

    @staticmethod
    def logout(request: HttpRequest) -> None:
        logout(request)

    @staticmethod
    def request_password_reset(command: PasswordResetRequest) -> None:
        user = AccountService._find_user(command.email)
        if user is None or not user.has_usable_password() or not user.email:
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
        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = get_user_model().objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist) as exc:
            raise PasswordResetTokenError("Password reset link is invalid or expired") from exc
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
