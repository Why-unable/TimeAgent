import json
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings

from apps.notifications.exceptions import (
    NotificationConfigurationError,
    PermanentNotificationError,
    TransientNotificationError,
)
from apps.notifications.models import NotificationChannelType
from apps.notifications.providers.base import NotificationMessage, ProviderSendResult


class WebPushNotificationProvider:
    channel_type = NotificationChannelType.WEB_PUSH

    def __init__(self, *, sender: Any | None = None) -> None:
        if sender is None:
            try:
                from pywebpush import webpush
            except ImportError as exc:  # pragma: no cover - deployment packaging guard
                raise NotificationConfigurationError("pywebpush is not installed") from exc
            sender = webpush
        self._sender = sender

    def send(self, message: NotificationMessage) -> ProviderSendResult:
        private_key = str(getattr(settings, "WEB_PUSH_VAPID_PRIVATE_KEY", "")).strip()
        subject = str(getattr(settings, "WEB_PUSH_VAPID_SUBJECT", "")).strip()
        if not private_key or not subject:
            raise NotificationConfigurationError("Web Push VAPID configuration is incomplete")
        if not message.web_push_targets:
            raise PermanentNotificationError("The current user has no active push subscription")

        data = json.dumps(
            {
                "title": message.subject,
                "body": message.body,
                **message.payload,
            },
            ensure_ascii=False,
        )
        accepted_ids: list[str] = []
        invalid_ids: list[str] = []
        for target in message.web_push_targets:
            try:
                requests_session = _build_proxy_session()
                try:
                    send_options = {
                        "subscription_info": {
                            "endpoint": target.endpoint,
                            "keys": {"p256dh": target.p256dh, "auth": target.auth},
                        },
                        "data": data,
                        "vapid_private_key": private_key,
                        "vapid_claims": {"sub": subject},
                        "timeout": int(getattr(settings, "WEB_PUSH_TIMEOUT_SECONDS", 10)),
                    }
                    if requests_session is not None:
                        send_options["requests_session"] = requests_session
                    response = self._sender(**send_options)
                finally:
                    if requests_session is not None:
                        requests_session.close()
            except Exception as exc:
                status_code = _status_code(exc)
                if status_code in {404, 410}:
                    invalid_ids.append(target.subscription_id)
                    continue
                if status_code == 429 or (status_code is not None and status_code >= 500):
                    raise TransientNotificationError(f"Web Push HTTP {status_code}") from exc
                if isinstance(exc, (TimeoutError, ConnectionError)) or type(exc).__name__ in {
                    "ConnectTimeout",
                    "ConnectionError",
                    "ReadTimeout",
                    "SoftTimeLimitExceeded",
                    "Timeout",
                }:
                    raise TransientNotificationError(type(exc).__name__) from exc
                raise PermanentNotificationError(
                    f"Web Push rejected the subscription ({status_code or type(exc).__name__})"
                ) from exc
            status_code = getattr(response, "status_code", 201)
            if status_code == 429 or status_code >= 500:
                raise TransientNotificationError(f"Web Push HTTP {status_code}")
            if status_code in {404, 410}:
                invalid_ids.append(target.subscription_id)
            elif 200 <= status_code < 300:
                accepted_ids.append(target.subscription_id)
            else:
                raise PermanentNotificationError(f"Web Push HTTP {status_code}")

        if not accepted_ids and not invalid_ids:
            raise TransientNotificationError("No Web Push endpoint accepted the notification")
        return ProviderSendResult(
            accepted=True,
            provider_message_id=",".join(accepted_ids)[:255],
            provider_status="accepted" if accepted_ids else "subscriptions_invalid",
            accepted_subscription_ids=tuple(accepted_ids),
            invalid_subscription_ids=tuple(invalid_ids),
        )


def _status_code(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def _build_proxy_session() -> Any | None:
    proxy_url = str(getattr(settings, "WEB_PUSH_HTTPS_PROXY", "")).strip()
    if not proxy_url:
        return None
    parsed = urlsplit(proxy_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise NotificationConfigurationError("WEB_PUSH_HTTPS_PROXY must be an HTTP(S) URL")
    import requests

    session = requests.Session()
    session.trust_env = False
    session.proxies.update({"http": proxy_url, "https": proxy_url})
    return session
