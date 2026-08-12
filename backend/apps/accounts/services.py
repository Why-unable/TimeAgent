from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import UUID, uuid4

from django.conf import settings
from django.contrib.auth import authenticate, get_user, get_user_model, login, logout
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

from apps.accounts.models import GuestAccount
from common.clock import Clock, SystemClock

logger = logging.getLogger(__name__)


class AuthenticationFailedError(ValueError):
    pass


class RegistrationDisabledError(ValueError):
    pass


class PasswordResetTokenError(ValueError):
    pass


class EmailVerificationTokenError(ValueError):
    pass


class GuestAccessDisabledError(ValueError):
    pass


class GuestAccountExpiredError(ValueError):
    pass


class GuestQuotaExceededError(ValueError):
    pass


class GuestFeatureUnavailableError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PasswordResetRequest:
    email: str
    application_url: str


@dataclass(frozen=True, slots=True)
class EmailVerificationRequest:
    email: str
    application_url: str


class GuestAccountPolicyService:
    RESOURCE_SETTINGS = {
        "conversation": ("GUEST_MAX_CONVERSATIONS", "会话"),
        "event": ("GUEST_MAX_EVENTS", "日程"),
        "task": ("GUEST_MAX_TASKS", "任务"),
        "reminder": ("GUEST_MAX_REMINDERS", "提醒"),
        "briefing_definition": ("GUEST_MAX_BRIEFING_DEFINITIONS", "简报模板"),
    }

    @staticmethod
    def is_guest(user: User) -> bool:
        return GuestAccount.objects.filter(user=user).exists()

    @staticmethod
    def guest_account(user: User) -> GuestAccount | None:
        return GuestAccount.objects.filter(user=user).first()

    @staticmethod
    def assert_resource_creation_allowed(user: User, resource: str) -> None:
        guest_account = GuestAccountPolicyService._lock_active_guest(user)
        if guest_account is None:
            return
        setting_name, label = GuestAccountPolicyService.RESOURCE_SETTINGS[resource]
        limit = int(getattr(settings, setting_name))
        count = GuestAccountPolicyService._resource_count(user, resource)
        if count >= limit:
            raise GuestQuotaExceededError(f"游客体验最多可创建 {limit} 个{label}。")

    @staticmethod
    def assert_agent_run_allowed(user: User, *, operation_id: UUID) -> None:
        from apps.conversations.models import AgentRun

        if AgentRun.objects.filter(operation_id=operation_id, conversation__user=user).exists():
            return
        guest_account = GuestAccountPolicyService._lock_active_guest(user)
        if guest_account is None:
            return
        limit = int(settings.GUEST_AGENT_RUN_LIMIT)
        count = AgentRun.objects.filter(conversation__user=user).count()
        if count >= limit:
            raise GuestQuotaExceededError(f"游客体验最多可发起 {limit} 次智能助理或简报请求。")

    @staticmethod
    def validate_preference_changes(user: User, changes: Mapping[str, Any]) -> None:
        if not GuestAccountPolicyService.is_guest(user):
            return
        unavailable = {
            "daily_briefing_enabled",
            "time_memory_enabled",
            "time_memory_allow_generation",
            "time_memory_allow_context_injection",
        }
        if any(bool(changes.get(field)) for field in unavailable):
            raise GuestFeatureUnavailableError(
                "游客体验不启用定时简报或长期记忆，请注册正式账号后使用。"
            )

    @staticmethod
    def validate_notification_changes(user: User, changes: Mapping[str, bool]) -> None:
        if not GuestAccountPolicyService.is_guest(user):
            return
        external_fields = {
            "reminder_email_enabled",
            "reminder_web_push_enabled",
            "briefing_email_enabled",
            "briefing_web_push_enabled",
        }
        if any(bool(changes.get(field)) for field in external_fields):
            raise GuestFeatureUnavailableError("游客体验仅支持应用内通知，不发送邮件或 Web Push。")

    @staticmethod
    def assert_push_allowed(user: User) -> None:
        if GuestAccountPolicyService.is_guest(user):
            raise GuestFeatureUnavailableError("游客体验不保存 Web Push 订阅。")

    @staticmethod
    def assert_reminder_channel_allowed(user: User, channel: object) -> None:
        if GuestAccountPolicyService.is_guest(user) and str(channel) != "console":
            raise GuestFeatureUnavailableError("游客体验仅支持应用内提醒。")

    @staticmethod
    def _lock_active_guest(user: User) -> GuestAccount | None:
        guest_account = GuestAccount.objects.select_for_update().filter(user=user).first()
        if guest_account is None:
            return None
        if guest_account.expires_at <= SystemClock().now_utc():
            raise GuestAccountExpiredError("游客体验已过期，请重新进入游客体验。")
        return guest_account

    @staticmethod
    def _resource_count(user: User, resource: str) -> int:
        if resource == "conversation":
            from apps.conversations.models import Conversation

            return Conversation.objects.filter(user=user).count()
        if resource == "event":
            from apps.events.models import CalendarEvent

            return CalendarEvent.objects.filter(user=user).count()
        if resource == "task":
            from apps.tasks.models import Task

            return Task.objects.filter(user=user).count()
        if resource == "reminder":
            from apps.reminders.models import Reminder

            return Reminder.objects.filter(user=user).count()
        if resource == "briefing_definition":
            from apps.briefings.models import BriefingDefinition

            return BriefingDefinition.objects.filter(user=user).count()
        raise ValueError(f"Unknown guest resource: {resource}")


class AccountService:
    @staticmethod
    @transaction.atomic
    def start_guest_session(
        request: HttpRequest,
        *,
        clock: Clock | None = None,
    ) -> User:
        if not settings.GUEST_ACCESS_ENABLED:
            raise GuestAccessDisabledError("游客体验当前未开放。")
        session_user = get_user(request)
        current_user = session_user if isinstance(session_user, User) else None
        if current_user is not None:
            guest_account = GuestAccountPolicyService.guest_account(current_user)
            if guest_account is None:
                raise GuestFeatureUnavailableError("请先退出当前账号，再进入游客体验。")
            if guest_account.expires_at > (clock or SystemClock()).now_utc():
                login(
                    request,
                    current_user,
                    backend="django.contrib.auth.backends.ModelBackend",
                )
                return current_user
            logout(request)
        user = AccountService.create_guest(clock=clock)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return user

    @staticmethod
    @transaction.atomic
    def create_guest(*, clock: Clock | None = None) -> User:
        if not settings.GUEST_ACCESS_ENABLED:
            raise GuestAccessDisabledError("游客体验当前未开放。")
        ttl_hours = int(settings.GUEST_ACCOUNT_TTL_HOURS)
        if ttl_hours <= 0:
            raise ValueError("GUEST_ACCOUNT_TTL_HOURS must be positive")
        current_at = (clock or SystemClock()).now_utc()
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username=f"guest-{uuid4().hex}@guest.invalid",
            email="",
            first_name="游客",
            is_active=True,
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
        GuestAccount.objects.create(
            user=user,
            expires_at=current_at + timedelta(hours=ttl_hours),
        )
        AccountService._seed_guest_workspace(user=user, current_at=current_at)
        logger.info("guest_account_created", extra={"user_id": user.pk})
        return user

    @staticmethod
    def cleanup_expired_guests(*, batch_size: int = 100) -> int:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        from apps.agents.memory.persistence import open_langgraph_persistence
        from apps.conversations.models import Conversation
        from apps.time_memory.repository import TimeMemoryRepository

        current_at = SystemClock().now_utc()
        with transaction.atomic():
            guest_accounts = list(
                GuestAccount.objects.select_for_update(skip_locked=True)
                .select_related("user")
                .filter(expires_at__lte=current_at)
                .order_by("expires_at")[:batch_size]
            )
            for guest_account in guest_accounts:
                if guest_account.user.is_active:
                    guest_account.user.is_active = False
                    guest_account.user.save(update_fields=["is_active"])
        if not guest_accounts:
            return 0

        with open_langgraph_persistence() as persistence:
            for guest_account in guest_accounts:
                user_id = guest_account.user_id
                conversation_ids = Conversation.objects.filter(user_id=user_id).values_list(
                    "id", flat=True
                )
                for conversation_id in conversation_ids:
                    persistence.checkpointer.delete_thread(str(conversation_id))
                TimeMemoryRepository.delete(persistence.store, user_id=str(user_id))

        user_ids = [guest_account.user_id for guest_account in guest_accounts]
        with transaction.atomic():
            deleted_count = (
                get_user_model()
                .objects.filter(
                    pk__in=user_ids,
                    guest_account__expires_at__lte=current_at,
                )
                .count()
            )
            get_user_model().objects.filter(
                pk__in=user_ids,
                guest_account__expires_at__lte=current_at,
            ).delete()
        logger.info("expired_guest_accounts_deleted", extra={"count": deleted_count})
        return deleted_count

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
    def verify_credentials(request: HttpRequest | None, *, identifier: str, password: str) -> User:
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

    @staticmethod
    def _seed_guest_workspace(*, user: User, current_at: datetime) -> None:
        from apps.events.services import CreateEventCommand, EventService
        from apps.preferences.services import UserPreferenceService
        from apps.reminders.services import CreateReminderCommand, ReminderService
        from apps.tasks.services import CreateTaskCommand, TaskService

        timezone_name = settings.DEFAULT_USER_TIMEZONE
        UserPreferenceService.update_for_user(
            user,
            {
                "daily_briefing_enabled": False,
                "time_memory_enabled": False,
                "time_memory_allow_generation": False,
                "time_memory_allow_context_injection": False,
            },
        )
        TaskService.create_task(
            CreateTaskCommand(
                user=user,
                title="[示例] 整理今天最重要的三件事",
                due_at=current_at + timedelta(hours=6),
                estimated_minutes=30,
                source="guest_seed",
                origin="guest_seed",
            )
        )
        EventService.create_event(
            CreateEventCommand(
                user=user,
                title="[示例] 专注处理重要事项",
                start_at=current_at + timedelta(hours=2),
                end_at=current_at + timedelta(hours=2, minutes=45),
                timezone=timezone_name,
                source="local",
                origin="guest_seed",
            )
        )
        ReminderService.create_reminder(
            CreateReminderCommand(
                user=user,
                title="[示例] 查看 Time Agent 使用指引",
                trigger_at=current_at + timedelta(hours=1),
                timezone=timezone_name,
                deduplication_key=f"guest-seed-guide-{user.pk}",
                origin="guest_seed",
            )
        )
