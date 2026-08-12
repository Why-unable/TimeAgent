from django.contrib.auth import logout
from django.contrib.auth.models import User
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from apps.accounts.models import GuestAccount
from common.clock import SystemClock


def _is_expired_guest(user: User) -> bool:
    guest_account = GuestAccount.objects.filter(user=user).only("expires_at").first()
    if guest_account is None:
        return False
    return guest_account.expires_at <= SystemClock().now_utc()


class ActiveAccountTokenAuthentication(TokenAuthentication):
    def authenticate_credentials(self, key: str) -> tuple[User, Token]:
        user, token = super().authenticate_credentials(key)
        if _is_expired_guest(user):
            raise AuthenticationFailed("游客体验已过期，请重新进入游客体验。")
        return user, token


class ActiveAccountSessionAuthentication(SessionAuthentication):
    def authenticate(self, request: Request) -> tuple[User, None] | None:
        result = super().authenticate(request)
        if result is None:
            return None
        user, auth = result
        if not isinstance(user, User):
            return None
        if _is_expired_guest(user):
            logout(request._request)
            return None
        return user, auth
