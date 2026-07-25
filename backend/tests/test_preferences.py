from datetime import time

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client

from apps.preferences.models import UserPreference
from apps.preferences.services import UserPreferenceService

pytestmark = pytest.mark.django_db


def create_user(username: str = "phase1-user") -> User:
    return get_user_model().objects.create_user(username=username, password="test-password")


def test_service_creates_default_preference() -> None:
    user = create_user()

    preference = UserPreferenceService.get_or_create_for_user(user)

    assert preference.timezone == "Asia/Shanghai"
    assert preference.locale == "zh-CN"
    assert preference.workday_start == time(9, 0)
    assert UserPreference.objects.filter(user=user).count() == 1


def test_service_builds_a_bounded_planning_snapshot() -> None:
    user = create_user()
    UserPreferenceService.update_for_user(
        user,
        {
            "workday_start": time(8, 30),
            "workday_end": time(17, 30),
            "preferred_focus_periods": ["09:00-11:00", {"ignore": "me"}],
            "default_reminder_offsets": [30, 120],
            "planning_rules": {"avoid_late_meetings": True, "invalid-key": "ignore"},
        },
    )

    snapshot = UserPreferenceService.planning_snapshot_for_user(user)

    assert snapshot.workday_start == "08:30"
    assert snapshot.workday_end == "17:30"
    assert snapshot.preferred_focus_periods == ("09:00-11:00",)
    assert snapshot.default_reminder_offsets == (30, 120)
    assert snapshot.planning_rules == (("avoid_late_meetings", "true"),)


def test_service_updates_preference_after_validation() -> None:
    user = create_user()

    preference = UserPreferenceService.update_for_user(
        user,
        {
            "timezone": "Europe/London",
            "locale": "en-GB",
            "default_event_duration_minutes": 45,
            "weather_forecast_days": 7,
        },
    )

    assert preference.timezone == "Europe/London"
    assert preference.locale == "en-GB"
    assert preference.default_event_duration_minutes == 45
    assert preference.weather_forecast_days == 7


def test_service_rejects_fields_outside_the_application_contract() -> None:
    user = create_user()

    with pytest.raises(ValueError, match="Unsupported preference fields"):
        UserPreferenceService.update_for_user(user, {"user_id": 999})


def test_model_rejects_invalid_timezone_and_workday() -> None:
    user = create_user()
    preference = UserPreference(
        user=user,
        timezone="UTC+8",
        workday_start=time(18, 0),
        workday_end=time(9, 0),
    )

    with pytest.raises(ValidationError) as error:
        preference.full_clean()

    assert "timezone" in error.value.message_dict
    assert "workday_end" in error.value.message_dict


def test_preference_api_requires_authentication() -> None:
    response = Client().get("/api/v1/preferences/me/")

    assert response.status_code in (401, 403)


def test_preference_api_reads_and_updates_via_service() -> None:
    user = create_user()
    client = Client()
    client.force_login(user)

    get_response = client.get("/api/v1/preferences/me/")
    patch_response = client.patch(
        "/api/v1/preferences/me/",
        data={
            "timezone": "America/Los_Angeles",
            "locale": "en-US",
            "workday_start": "08:30:00",
            "workday_end": "17:30:00",
            "default_event_duration_minutes": 30,
            "weather_forecast_days": 5,
        },
        content_type="application/json",
    )

    assert get_response.status_code == 200
    assert get_response.json()["timezone"] == "Asia/Shanghai"
    assert patch_response.status_code == 200
    assert patch_response.json()["timezone"] == "America/Los_Angeles"
    assert patch_response.json()["weather_forecast_days"] == 5
    assert UserPreference.objects.get(user=user).default_event_duration_minutes == 30


def test_preference_api_rejects_invalid_timezone() -> None:
    user = create_user()
    client = Client()
    client.force_login(user)

    response = client.patch(
        "/api/v1/preferences/me/",
        data={"timezone": "UTC+8"},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "timezone" in response.json()
