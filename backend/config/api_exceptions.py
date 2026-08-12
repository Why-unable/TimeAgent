from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.accounts.services import (
    GuestAccountExpiredError,
    GuestFeatureUnavailableError,
    GuestQuotaExceededError,
)
from apps.events.services import PastEventMutationError


def time_agent_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, GuestQuotaExceededError):
        return Response({"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    if isinstance(exc, GuestFeatureUnavailableError):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    if isinstance(exc, GuestAccountExpiredError):
        return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
    if isinstance(exc, PastEventMutationError):
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    return exception_handler(exc, context)
