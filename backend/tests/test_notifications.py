from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from celery.exceptions import Retry
from django.contrib.auth.models import User
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.test import override_settings
from requests import Session
from rest_framework.test import APIClient

from apps.briefings.models import BriefingRun, BriefingRunStatus
from apps.briefings.services import BriefingDefinitionService
from apps.notifications.dispatcher import NotificationDispatcher
from apps.notifications.exceptions import (
    NotificationProviderNotRegisteredError,
    PermanentNotificationError,
    TransientNotificationError,
)
from apps.notifications.integrations import create_briefing_deliveries
from apps.notifications.models import (
    NotificationChannelType,
    NotificationDeliveryStatus,
    NotificationSourceType,
    WebPushSubscription,
)
from apps.notifications.providers.base import (
    NotificationMessage,
    ProviderSendResult,
    WebPushTarget,
)
from apps.notifications.providers.console import ConsoleNotificationProvider
from apps.notifications.providers.email import EmailNotificationProvider
from apps.notifications.providers.registry import NotificationProviderRegistry
from apps.notifications.providers.web_push import WebPushNotificationProvider
from apps.notifications.services import (
    CreateDeliveryCommand,
    NotificationIdempotencyConflictError,
    NotificationService,
)
from apps.notifications.tasks import send_notification_delivery

pytestmark = pytest.mark.django_db
NOW = datetime(2026, 7, 21, 1, 0, tzinfo=UTC)


def user(name: str = "notification-user", *, email: str = "user@example.test") -> User:
    return User.objects.create_user(username=name, email=email)


def command(
    owner: User, *, key: str = "system:test:console", channel: str = "console"
) -> CreateDeliveryCommand:
    return CreateDeliveryCommand(
        user=owner,
        source_type=NotificationSourceType.SYSTEM,
        source_id=None,
        channel_type=channel,
        deduplication_key=key,
        subject="Test notification",
        body="Body",
        scheduled_at=NOW,
        payload={"url": "/"},
    )


def test_delivery_state_machine_and_illegal_transition() -> None:
    delivery = NotificationService.create_delivery(command(user()))
    delivery = NotificationService.queue_delivery(delivery_id=delivery.id, occurred_at=NOW)
    sending_delivery = NotificationService.mark_sending(delivery_id=delivery.id, occurred_at=NOW)
    assert sending_delivery is not None
    delivery = NotificationService.mark_sent(
        delivery_id=sending_delivery.id,
        occurred_at=NOW,
        provider_message_id="provider-1",
    )
    assert delivery.status == NotificationDeliveryStatus.SENT
    assert delivery.attempt_count == 1
    with pytest.raises(ValueError, match="cannot be queued"):
        NotificationService.queue_delivery(delivery_id=delivery.id, occurred_at=NOW)


def test_delivery_creation_is_idempotent_and_detects_conflict() -> None:
    owner = user()
    first = NotificationService.create_delivery(command(owner))
    duplicate = NotificationService.create_delivery(command(owner))
    assert duplicate.pk == first.pk
    with pytest.raises(NotificationIdempotencyConflictError):
        NotificationService.create_delivery(command(owner, channel="email"))


def test_registry_and_console_provider(caplog: pytest.LogCaptureFixture) -> None:
    provider = ConsoleNotificationProvider()
    registry = NotificationProviderRegistry((provider,))
    message = NotificationMessage(
        delivery_id="delivery",
        user_id="42",
        subject="Subject",
        body="private body",
        payload={},
        idempotency_key="stable-key",
    )
    with caplog.at_level("INFO"):
        result = registry.get("console").send(message)
    assert result.accepted is True
    assert result.provider_message_id == "stable-key"
    assert "private body" not in caplog.text
    with pytest.raises(NotificationProviderNotRegisteredError):
        registry.get("email")


@override_settings(EMAIL_FROM_ADDRESS="Time Agent <noreply@example.test>")
def test_email_provider_uses_current_user_recipient_and_returns_message_id() -> None:
    result = EmailNotificationProvider().send(
        NotificationMessage(
            delivery_id="d1",
            user_id="1",
            subject="Subject",
            body="Body",
            payload={},
            idempotency_key="email-key",
            recipient_email="user@example.test",
        )
    )
    assert result.accepted is True
    assert result.provider_message_id.startswith("<")
    sent_email = cast(EmailMultiAlternatives, mail.outbox[0])
    assert sent_email.to == ["user@example.test"]
    assert sent_email.subject == "Subject"
    _, mimetype = sent_email.alternatives[0]
    assert mimetype == "text/html"


@override_settings(EMAIL_FROM_ADDRESS="Time Agent <noreply@example.test>")
def test_email_provider_renders_safe_briefing_html() -> None:
    EmailNotificationProvider().send(
        NotificationMessage(
            delivery_id="d2",
            user_id="1",
            subject="Briefing",
            body=(
                "# 每日简报\n\n## 天气\n\n- **高州市**：雷阵雨\n"
                "- [可信来源](https://example.test/news)\n"
                "- [不安全链接](javascript:alert(1)) <script>alert(1)</script>"
            ),
            payload={},
            idempotency_key="briefing-email-key",
            recipient_email="user@example.test",
        )
    )

    sent_email = cast(EmailMultiAlternatives, mail.outbox[0])
    html_body = cast(str, sent_email.alternatives[0][0])
    assert "<h1" in html_body
    assert "<h2" in html_body
    assert "<strong>高州市</strong>" in html_body
    assert 'href="https://example.test/news"' in html_body
    assert "javascript:" not in html_body
    assert "<script>" not in html_body
    assert "&lt;script&gt;" in html_body


def test_email_provider_rejects_missing_current_user_email() -> None:
    with pytest.raises(PermanentNotificationError, match="valid email"):
        EmailNotificationProvider().send(
            NotificationMessage(
                delivery_id="d1",
                user_id="1",
                subject="Subject",
                body="Body",
                payload={},
                idempotency_key="email-key",
            )
        )


@override_settings(
    WEB_PUSH_VAPID_PRIVATE_KEY="private", WEB_PUSH_VAPID_SUBJECT="mailto:test@example.test"
)
def test_web_push_invalid_subscription_is_reported_without_leaking_secret() -> None:
    class Response:
        status_code = 410

    result = WebPushNotificationProvider(sender=lambda **kwargs: Response()).send(
        NotificationMessage(
            delivery_id="d1",
            user_id="1",
            subject="Subject",
            body="Body",
            payload={"url": "/reminders"},
            idempotency_key="push-key",
            web_push_targets=(
                WebPushTarget(
                    subscription_id="sub-1",
                    endpoint="https://push.example.test/secret",
                    p256dh="key",
                    auth="auth",
                ),
            ),
        )
    )
    assert result.invalid_subscription_ids == ("sub-1",)


@override_settings(
    WEB_PUSH_VAPID_PRIVATE_KEY="private", WEB_PUSH_VAPID_SUBJECT="mailto:test@example.test"
)
def test_web_push_soft_time_limit_is_retryable() -> None:
    class SoftTimeLimitExceeded(Exception):
        pass

    def timeout_sender(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        raise SoftTimeLimitExceeded

    with pytest.raises(TransientNotificationError, match="SoftTimeLimitExceeded"):
        WebPushNotificationProvider(sender=timeout_sender).send(
            NotificationMessage(
                delivery_id="d1",
                user_id="1",
                subject="Subject",
                body="Body",
                payload={},
                idempotency_key="push-timeout",
                web_push_targets=(
                    WebPushTarget(
                        subscription_id="sub-1",
                        endpoint="https://push.example.test/timeout",
                        p256dh="key",
                        auth="auth",
                    ),
                ),
            )
        )


@override_settings(
    WEB_PUSH_VAPID_PRIVATE_KEY="private",
    WEB_PUSH_VAPID_SUBJECT="mailto:test@example.test",
    WEB_PUSH_HTTPS_PROXY="http://proxy.example.test:8080",
)
def test_web_push_uses_configured_https_proxy() -> None:
    captured: dict[str, object] = {}

    class Response:
        status_code = 201

    def sender(**kwargs: object) -> Response:
        captured.update(kwargs)
        return Response()

    result = WebPushNotificationProvider(sender=sender).send(
        NotificationMessage(
            delivery_id="d1",
            user_id="1",
            subject="Subject",
            body="Body",
            payload={},
            idempotency_key="push-proxy",
            web_push_targets=(
                WebPushTarget(
                    subscription_id="sub-1",
                    endpoint="https://fcm.googleapis.com/fcm/send/example",
                    p256dh="key",
                    auth="auth",
                ),
            ),
        )
    )

    assert result.accepted is True
    session = captured["requests_session"]
    assert isinstance(session, Session)
    assert session.proxies == {
        "http": "http://proxy.example.test:8080",
        "https": "http://proxy.example.test:8080",
    }


def test_api_isolates_deliveries_and_push_subscriptions() -> None:
    owner = user("owner")
    other = user("other")
    delivery = NotificationService.create_delivery(command(owner))
    other_delivery = NotificationService.create_delivery(command(other))
    subscription = NotificationService.save_push_subscription(
        user=owner,
        endpoint="https://push.example.test/owner",
        p256dh="p256dh",
        auth="auth",
        user_agent="pytest",
    )
    client = APIClient()
    client.force_authenticate(owner)
    response = client.get("/api/v1/notification-deliveries/")
    assert response.status_code == 200
    assert [item["id"] for item in response.data] == [str(delivery.id)]
    assert client.get(f"/api/v1/notification-deliveries/{other_delivery.id}/").status_code == 404
    push_response = client.get("/api/v1/web-push/subscriptions/")
    assert push_response.status_code == 200
    assert push_response.data[0]["id"] == str(subscription.id)
    assert "auth" not in push_response.data[0]
    assert "p256dh" not in push_response.data[0]

    other_client = APIClient()
    other_client.force_authenticate(other)
    claim = other_client.post(
        "/api/v1/web-push/subscriptions/",
        {
            "endpoint": "https://push.example.test/owner",
            "p256dh": "other-key",
            "auth": "other-auth",
        },
        format="json",
    )
    assert claim.status_code == 400
    assert claim.data == {"endpoint": "Subscription cannot be claimed"}


def test_unsubscribe_removes_only_the_current_browser_endpoint() -> None:
    owner = user("owner")
    other = user("other")
    current = NotificationService.save_push_subscription(
        user=owner,
        endpoint="https://push.example.test/current-browser",
        p256dh="current-key",
        auth="current-auth",
        user_agent="current browser",
    )
    retained = NotificationService.save_push_subscription(
        user=owner,
        endpoint="https://push.example.test/other-browser",
        p256dh="other-key",
        auth="other-auth",
        user_agent="other browser",
    )
    other_user_subscription = NotificationService.save_push_subscription(
        user=other,
        endpoint="https://push.example.test/other-user",
        p256dh="other-user-key",
        auth="other-user-auth",
        user_agent="other user browser",
    )
    client = APIClient()
    client.force_authenticate(owner)

    response = client.post(
        "/api/v1/web-push/subscriptions/unsubscribe/",
        {"endpoint": current.endpoint},
        format="json",
    )

    assert response.status_code == 204
    assert not WebPushSubscription.objects.filter(pk=current.pk).exists()
    assert WebPushSubscription.objects.filter(pk=retained.pk).exists()
    assert WebPushSubscription.objects.filter(pk=other_user_subscription.pk).exists()
    assert (
        client.post(
            "/api/v1/web-push/subscriptions/unsubscribe/",
            {"endpoint": current.endpoint},
            format="json",
        ).status_code
        == 204
    )


def test_preferences_are_user_isolated_and_update_channels() -> None:
    owner = user()
    client = APIClient()
    client.force_authenticate(owner)
    response = client.patch(
        "/api/v1/notification-preferences/me/", {"reminder_email_enabled": True}, format="json"
    )
    assert response.status_code == 200
    assert response.data["reminder_email_enabled"] is True
    assert NotificationService.channels_for(
        user=owner, source_type=NotificationSourceType.REMINDER
    ) == (NotificationChannelType.CONSOLE, NotificationChannelType.EMAIL)


def test_invalidate_push_subscription() -> None:
    owner = user()
    item = NotificationService.save_push_subscription(
        user=owner,
        endpoint="https://push.example.test/one",
        p256dh="key",
        auth="auth",
        user_agent="pytest",
    )
    NotificationService.invalidate_push_subscriptions(subscription_ids=(str(item.id),))
    item.refresh_from_db()
    assert item.enabled is False
    assert item.invalidated_at is not None


def test_dispatcher_queues_due_delivery_once(
    django_capture_on_commit_callbacks: object,
) -> None:
    owner = user()
    delivery = NotificationService.create_delivery(command(owner))
    queued: list[object] = []
    capture = django_capture_on_commit_callbacks
    with capture(execute=True):  # type: ignore[operator]
        assert NotificationDispatcher.queue_due_deliveries(now=NOW, enqueue=queued.append) == 1
    delivery.refresh_from_db()
    assert delivery.status == NotificationDeliveryStatus.QUEUED
    assert queued == [delivery.id]
    # Recovery scans re-enqueue queued records; task state locking makes this safe.
    assert NotificationDispatcher.queue_due_deliveries(now=NOW, enqueue=queued.append) == 1


def test_duplicate_delivery_task_does_not_send_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = user()
    delivery = NotificationService.create_delivery(command(owner))
    NotificationService.queue_delivery(delivery_id=delivery.id, occurred_at=NOW)
    calls = 0

    class Provider:
        channel_type = NotificationChannelType.CONSOLE

        def send(self, message: NotificationMessage) -> ProviderSendResult:
            nonlocal calls
            calls += 1
            return ProviderSendResult(True, "provider-1", "accepted")

    monkeypatch.setattr(
        "apps.notifications.tasks.build_default_registry",
        lambda: NotificationProviderRegistry((Provider(),)),
    )
    assert send_notification_delivery.run(str(delivery.id)) is True
    assert send_notification_delivery.run(str(delivery.id)) is False
    assert calls == 1


@override_settings(NOTIFICATION_MAX_RETRIES=0)
def test_transient_error_stops_at_retry_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = user()
    delivery = NotificationService.create_delivery(command(owner))
    NotificationService.queue_delivery(delivery_id=delivery.id, occurred_at=NOW)

    class Provider:
        channel_type = NotificationChannelType.CONSOLE

        def send(self, message: NotificationMessage) -> ProviderSendResult:
            del message
            raise TransientNotificationError("temporary outage")

    monkeypatch.setattr(
        "apps.notifications.tasks.build_default_registry",
        lambda: NotificationProviderRegistry((Provider(),)),
    )
    assert send_notification_delivery.run(str(delivery.id)) is False
    delivery.refresh_from_db()
    assert delivery.status == NotificationDeliveryStatus.FAILED
    assert delivery.attempt_count == 1
    assert delivery.next_retry_at is None


def test_permanent_error_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = user()
    delivery = NotificationService.create_delivery(command(owner))
    NotificationService.queue_delivery(delivery_id=delivery.id, occurred_at=NOW)

    class Provider:
        channel_type = NotificationChannelType.CONSOLE

        def send(self, message: NotificationMessage) -> ProviderSendResult:
            del message
            raise PermanentNotificationError("invalid recipient")

    monkeypatch.setattr(
        "apps.notifications.tasks.build_default_registry",
        lambda: NotificationProviderRegistry((Provider(),)),
    )
    assert send_notification_delivery.run(str(delivery.id)) is False
    delivery.refresh_from_db()
    assert delivery.status == NotificationDeliveryStatus.FAILED
    assert delivery.failure_code == "permanent_notification_error"


def test_transient_error_is_requeued_before_celery_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = user()
    delivery = NotificationService.create_delivery(command(owner))
    NotificationService.queue_delivery(delivery_id=delivery.id, occurred_at=NOW)

    class Provider:
        channel_type = NotificationChannelType.CONSOLE

        def send(self, message: NotificationMessage) -> ProviderSendResult:
            del message
            raise TransientNotificationError("temporary outage")

    monkeypatch.setattr(
        "apps.notifications.tasks.build_default_registry",
        lambda: NotificationProviderRegistry((Provider(),)),
    )
    monkeypatch.setattr(
        send_notification_delivery,
        "retry",
        lambda **kwargs: (_ for _ in ()).throw(Retry()),
    )
    with pytest.raises(Retry):
        send_notification_delivery.run(str(delivery.id))
    delivery.refresh_from_db()
    assert delivery.status == NotificationDeliveryStatus.QUEUED
    assert delivery.attempt_count == 1


def test_invalid_push_result_disables_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = user()
    subscription = NotificationService.save_push_subscription(
        user=owner,
        endpoint="https://push.example.test/invalid",
        p256dh="key",
        auth="auth",
        user_agent="pytest",
    )
    delivery = NotificationService.create_delivery(
        command(owner, key="system:test:web-push", channel="web_push")
    )
    NotificationService.queue_delivery(delivery_id=delivery.id, occurred_at=NOW)

    class Provider:
        channel_type = NotificationChannelType.WEB_PUSH

        def send(self, message: NotificationMessage) -> ProviderSendResult:
            del message
            return ProviderSendResult(
                accepted=True,
                provider_message_id="",
                provider_status="subscriptions_invalid",
                invalid_subscription_ids=(str(subscription.id),),
            )

    monkeypatch.setattr(
        "apps.notifications.tasks.build_default_registry",
        lambda: NotificationProviderRegistry((Provider(),)),
    )
    assert send_notification_delivery.run(str(delivery.id)) is True
    subscription.refresh_from_db()
    delivery.refresh_from_db()
    assert subscription.enabled is False
    assert subscription.invalidated_at is not None
    assert delivery.status == NotificationDeliveryStatus.SENT


def test_completed_briefing_creates_independent_channel_deliveries() -> None:
    owner = user()
    preference = NotificationService.get_or_create_preference(owner)
    preference.briefing_email_enabled = True
    preference.save()
    definition = BriefingDefinitionService.default_for_user(owner)
    run = BriefingRun.objects.create(
        definition=definition,
        user=owner,
        operation_id=uuid4(),
        trigger_type="scheduled_briefing",
        target_date=NOW.date(),
        timezone="Asia/Shanghai",
        status=BriefingRunStatus.COMPLETED,
        rendered_markdown="# Daily briefing",
    )
    deliveries = create_briefing_deliveries(run=run, occurred_at=NOW)
    assert {item.channel_type for item in deliveries} == {"console", "email"}
    assert all(item.status == NotificationDeliveryStatus.QUEUED for item in deliveries)


def test_completed_briefing_keeps_future_deliveries_pending() -> None:
    owner = user()
    definition = BriefingDefinitionService.default_for_user(owner)
    run = BriefingRun.objects.create(
        definition=definition,
        user=owner,
        operation_id=uuid4(),
        trigger_type="scheduled_briefing",
        target_date=NOW.date(),
        timezone="Asia/Shanghai",
        status=BriefingRunStatus.COMPLETED,
        rendered_markdown="# Daily briefing",
    )

    deliveries = create_briefing_deliveries(
        run=run,
        occurred_at=NOW,
        scheduled_at=NOW.replace(hour=NOW.hour + 1),
    )

    assert deliveries
    assert all(item.status == NotificationDeliveryStatus.PENDING for item in deliveries)


def test_failed_briefing_does_not_create_delivery() -> None:
    owner = user()
    definition = BriefingDefinitionService.default_for_user(owner)
    run = BriefingRun.objects.create(
        definition=definition,
        user=owner,
        operation_id=uuid4(),
        trigger_type="scheduled_briefing",
        target_date=NOW.date(),
        timezone="Asia/Shanghai",
        status=BriefingRunStatus.FAILED,
    )
    assert create_briefing_deliveries(run=run, occurred_at=NOW) == []
