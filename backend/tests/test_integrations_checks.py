from django.core.checks import run_checks
from django.test import override_settings


@override_settings(
    CALENDAR_OAUTH_FERNET_KEY="",
    GOOGLE_CALENDAR_CLIENT_ID="",
    GOOGLE_CALENDAR_CLIENT_SECRET="",
    GOOGLE_CALENDAR_REDIRECT_URI="",
)
def test_calendar_oauth_can_be_fully_disabled() -> None:
    errors = run_checks(tags=["security"])
    assert not [
        error
        for error in errors
        if error.id is not None and error.id.startswith("integrations.")
    ]


@override_settings(
    CALENDAR_OAUTH_FERNET_KEY="invalid",
    GOOGLE_CALENDAR_CLIENT_ID="client",
    GOOGLE_CALENDAR_CLIENT_SECRET="",
    GOOGLE_CALENDAR_REDIRECT_URI="http://localhost/callback",
    DEBUG=False,
)
def test_calendar_oauth_partial_configuration_fails_system_check() -> None:
    errors = run_checks(tags=["security"])
    assert {
        error.id
        for error in errors
        if error.id is not None and error.id.startswith("integrations.")
    } == {
        "integrations.E001"
    }


@override_settings(
    CALENDAR_OAUTH_FERNET_KEY="invalid",
    GOOGLE_CALENDAR_CLIENT_ID="client",
    GOOGLE_CALENDAR_CLIENT_SECRET="secret",
    GOOGLE_CALENDAR_REDIRECT_URI="http://localhost/callback",
    DEBUG=False,
)
def test_calendar_oauth_invalid_key_and_insecure_redirect_fail_system_check() -> None:
    errors = run_checks(tags=["security"])
    assert {
        error.id
        for error in errors
        if error.id is not None and error.id.startswith("integrations.")
    } == {
        "integrations.E002",
        "integrations.E004",
    }
