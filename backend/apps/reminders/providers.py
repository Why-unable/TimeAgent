"""Compatibility imports for the pre-Phase-9 module path.

New code must import providers from ``apps.notifications.providers``.
"""

from apps.notifications.providers import (  # noqa: F401
    NotificationMessage,
    NotificationProvider,
    ProviderSendResult,
)
from apps.notifications.providers.console import ConsoleNotificationProvider  # noqa: F401
