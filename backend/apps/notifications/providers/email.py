import re
import smtplib
from email.utils import make_msgid
from html import escape
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
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
        email = EmailMultiAlternatives(
            subject=message.subject,
            body=message.body,
            from_email=from_email,
            to=[recipient],
            headers={"Message-ID": message_id},
        )
        email.attach_alternative(_markdown_email_html(message.body), "text/html")
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


_LINK = re.compile(r"\[([^\]]+)]\(([^)]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")


def _markdown_email_html(markdown: str) -> str:
    parts = [
        '<div style="font-family:system-ui,-apple-system,sans-serif;color:#172033;',
        'font-size:16px;line-height:1.7;max-width:720px;margin:auto">',
    ]
    in_list = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            if in_list:
                parts.append("</ul>")
                in_list = False
            continue
        if line.startswith("- "):
            if not in_list:
                parts.append('<ul style="padding-left:1.4em">')
                in_list = True
            parts.append(f"<li>{_inline_markdown(line[2:])}</li>")
            continue
        if in_list:
            parts.append("</ul>")
            in_list = False
        heading_level = len(line) - len(line.lstrip("#"))
        if heading_level and heading_level <= 3 and line[heading_level:].startswith(" "):
            size = {1: "24px", 2: "20px", 3: "18px"}[heading_level]
            parts.append(
                f'<h{heading_level} style="font-size:{size};margin:1.2em 0 .4em">'
                f"{_inline_markdown(line[heading_level + 1 :])}</h{heading_level}>"
            )
        else:
            parts.append(f'<p style="margin:.65em 0">{_inline_markdown(line)}</p>')
    if in_list:
        parts.append("</ul>")
    parts.append("</div>")
    return "".join(parts)


def _inline_markdown(value: str) -> str:
    parts: list[str] = []
    cursor = 0
    for match in _LINK.finditer(value):
        parts.append(_bold_html(value[cursor : match.start()]))
        label = _bold_html(match.group(1))
        url = _safe_http_url(match.group(2))
        parts.append(
            f'<a href="{escape(url, quote=True)}" style="color:#0f766e">{label}</a>'
            if url
            else label
        )
        cursor = match.end()
    parts.append(_bold_html(value[cursor:]))
    return "".join(parts)


def _bold_html(value: str) -> str:
    parts: list[str] = []
    cursor = 0
    for match in _BOLD.finditer(value):
        parts.append(escape(value[cursor : match.start()]))
        parts.append(f"<strong>{escape(match.group(1))}</strong>")
        cursor = match.end()
    parts.append(escape(value[cursor:]))
    return "".join(parts)


def _safe_http_url(value: str) -> str:
    normalized = value.strip()
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.username or parsed.password:
        return ""
    return normalized
