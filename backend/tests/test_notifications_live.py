import os
from uuid import uuid4

import pytest

from apps.notifications.providers.base import NotificationMessage, WebPushTarget
from apps.notifications.providers.email import EmailNotificationProvider
from apps.notifications.providers.web_push import WebPushNotificationProvider

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_NOTIFICATION_TESTS") != "1",
    reason="Live notification tests require RUN_LIVE_NOTIFICATION_TESTS=1",
)


def test_live_email_to_explicit_test_user() -> None:
    recipient = os.environ["LIVE_NOTIFICATION_EMAIL"]
    result = EmailNotificationProvider().send(
        NotificationMessage(
            delivery_id=str(uuid4()),
            user_id="live-test-user",
            subject="Time Agent live email test",
            body="One explicitly enabled delivery from the Time Agent live test suite.",
            payload={},
            idempotency_key=f"live-email:{uuid4()}",
            recipient_email=recipient,
        )
    )
    assert result.accepted is True


def test_live_web_push_to_explicit_test_subscription() -> None:
    result = WebPushNotificationProvider().send(
        NotificationMessage(
            delivery_id=str(uuid4()),
            user_id="live-test-user",
            subject="Time Agent live Web Push test",
            body="One explicitly enabled delivery from the Time Agent live test suite.",
            payload={"url": "/settings/notifications"},
            idempotency_key=f"live-push:{uuid4()}",
            web_push_targets=(
                WebPushTarget(
                    subscription_id="live-test-subscription",
                    endpoint=os.environ["LIVE_WEB_PUSH_ENDPOINT"],
                    p256dh=os.environ["LIVE_WEB_PUSH_P256DH"],
                    auth=os.environ["LIVE_WEB_PUSH_AUTH"],
                ),
            ),
        )
    )
    assert result.accepted is True
