import smtplib
from email.utils import make_msgid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.validators import validate_email

from apps.notifications.exceptions import (
    NotificationConfigurationError,
    PermanentNotificationError,
    TransientNotificationError,
)
from apps.notifications.models import NotificationChannelType
from apps.notifications.providers.base import NotificationMessage, ProviderSendResult


class EmailNotificationProvider:
    channel_type = NotificationChannelType.EMAIL

    def send(self, message: NotificationMessage) -> ProviderSendResult:
        recipient = message.recipient_email.strip()
        try:
            validate_email(recipient)
        except ValidationError as exc:
            raise PermanentNotificationError(
                "The current user does not have a valid email"
            ) from exc
        from_email = str(getattr(settings, "EMAIL_FROM_ADDRESS", "")).strip()
        if not from_email:
            raise NotificationConfigurationError("EMAIL_FROM_ADDRESS is not configured")
        message_id = make_msgid(domain="time-agent.local")
        email = EmailMessage(
            subject=message.subject,
            body=message.body,
            from_email=from_email,
            to=[recipient],
            headers={"Message-ID": message_id},
        )
        try:
            sent = email.send(fail_silently=False)
        except (OSError, smtplib.SMTPServerDisconnected) as exc:
            raise TransientNotificationError(type(exc).__name__) from exc
        except smtplib.SMTPResponseException as exc:
            if 400 <= exc.smtp_code < 500:
                raise TransientNotificationError(f"SMTP {exc.smtp_code}") from exc
            raise PermanentNotificationError(f"SMTP {exc.smtp_code}") from exc
        except smtplib.SMTPException as exc:
            raise PermanentNotificationError(type(exc).__name__) from exc
        if sent != 1:
            raise TransientNotificationError("Email backend did not accept the message")
        return ProviderSendResult(
            accepted=True,
            provider_message_id=message_id,
            provider_status="accepted",
        )
