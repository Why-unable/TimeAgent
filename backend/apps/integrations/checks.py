from urllib.parse import urlparse

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.checks import Error, Tags, register


@register()
def check_calendar_poll_configuration(**kwargs: object) -> list[Error]:
    del kwargs
    bounds = {
        "CALENDAR_POLL_INTERVAL_SECONDS": (settings.CALENDAR_POLL_INTERVAL_SECONDS, 30, 86400),
        "CALENDAR_POLL_BATCH_SIZE": (settings.CALENDAR_POLL_BATCH_SIZE, 1, 1000),
        "CALENDAR_POLL_LOOKBACK_DAYS": (settings.CALENDAR_POLL_LOOKBACK_DAYS, 0, 3650),
        "CALENDAR_POLL_LOOKAHEAD_DAYS": (settings.CALENDAR_POLL_LOOKAHEAD_DAYS, 1, 3650),
    }
    errors: list[Error] = []
    for name, (value, minimum, maximum) in bounds.items():
        if not minimum <= value <= maximum:
            errors.append(
                Error(
                    f"{name} must be between {minimum} and {maximum}",
                    id="integrations.E006",
                )
            )
    return errors


@register(Tags.security)
def check_calendar_oauth_configuration(**kwargs: object) -> list[Error]:
    del kwargs
    values = {
        "CALENDAR_OAUTH_FERNET_KEY": settings.CALENDAR_OAUTH_FERNET_KEY,
        "GOOGLE_CALENDAR_CLIENT_ID": settings.GOOGLE_CALENDAR_CLIENT_ID,
        "GOOGLE_CALENDAR_CLIENT_SECRET": settings.GOOGLE_CALENDAR_CLIENT_SECRET,
        "GOOGLE_CALENDAR_REDIRECT_URI": settings.GOOGLE_CALENDAR_REDIRECT_URI,
    }
    any_primary_value = any(str(value).strip() for value in values.values())
    if not any_primary_value and not settings.CALENDAR_OAUTH_FERNET_OLD_KEYS:
        return []
    errors: list[Error] = []
    missing = [name for name, value in values.items() if not str(value).strip()]
    if missing:
        errors.append(
            Error(
                f"Google Calendar OAuth configuration is incomplete: {', '.join(missing)}",
                id="integrations.E001",
            )
        )
        return errors
    try:
        Fernet(str(settings.CALENDAR_OAUTH_FERNET_KEY).encode("ascii"))
    except (UnicodeEncodeError, ValueError):
        errors.append(
            Error(
                "CALENDAR_OAUTH_FERNET_KEY is not a valid Fernet key",
                id="integrations.E002",
            )
        )
    for old_key in settings.CALENDAR_OAUTH_FERNET_OLD_KEYS:
        try:
            Fernet(str(old_key).encode("ascii"))
        except (UnicodeEncodeError, ValueError):
            errors.append(
                Error(
                    "CALENDAR_OAUTH_FERNET_OLD_KEYS contains an invalid Fernet key",
                    id="integrations.E005",
                )
            )
            break
    redirect_uri = urlparse(str(settings.GOOGLE_CALENDAR_REDIRECT_URI))
    if redirect_uri.scheme not in {"http", "https"} or not redirect_uri.netloc:
        errors.append(
            Error(
                "GOOGLE_CALENDAR_REDIRECT_URI must be an absolute HTTP(S) URL",
                id="integrations.E003",
            )
        )
    elif not settings.DEBUG and redirect_uri.scheme != "https":
        errors.append(
            Error(
                "GOOGLE_CALENDAR_REDIRECT_URI must use HTTPS outside debug mode",
                id="integrations.E004",
            )
        )
    return errors
