from typing import Any

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from rest_framework.test import APIClient

from apps.app_updates.services import AndroidUpdateService


@pytest.mark.django_db
def test_android_update_manifest_is_authenticated_and_complete(settings: Any) -> None:
    settings.ANDROID_UPDATE_ENABLED = True
    settings.ANDROID_UPDATE_VERSION_CODE = 4
    settings.ANDROID_UPDATE_VERSION_NAME = "1.1.0"
    settings.ANDROID_UPDATE_DOWNLOAD_URL = (
        "https://steward.example.com/releases/timeagent-1.1.0.apk"
    )
    settings.ANDROID_UPDATE_SHA256 = "a" * 64
    settings.ANDROID_UPDATE_SIZE_BYTES = 12345
    settings.ANDROID_UPDATE_RELEASE_NOTES = "修复聊天错误提示。"
    settings.ANDROID_UPDATE_PUBLISHED_AT = "2026-08-07T00:00:00Z"
    settings.ANDROID_UPDATE_MINIMUM_SUPPORTED_VERSION_CODE = 3
    client = APIClient()
    assert client.get("/api/v1/app-updates/android/latest/").status_code in {401, 403}
    client.force_authenticate(User.objects.create_user(username="update-user"))
    response = client.get("/api/v1/app-updates/android/latest/")
    assert response.status_code == 200
    assert response.json()["release"]["version_code"] == 4
    assert response.json()["release"]["sha256"] == "a" * 64


def test_android_update_rejects_non_https_download(settings: Any) -> None:
    settings.ANDROID_UPDATE_ENABLED = True
    settings.ANDROID_UPDATE_DOWNLOAD_URL = "http://example.com/app.apk"
    settings.ANDROID_UPDATE_SHA256 = "a" * 64
    with pytest.raises(ImproperlyConfigured, match="HTTPS"):
        AndroidUpdateService.latest_release()


def test_android_update_rejects_invalid_release_metadata(settings: Any) -> None:
    settings.ANDROID_UPDATE_ENABLED = True
    settings.ANDROID_UPDATE_DOWNLOAD_URL = "https://example.com/app.apk"
    settings.ANDROID_UPDATE_SHA256 = "a" * 64
    settings.ANDROID_UPDATE_VERSION_CODE = 4
    settings.ANDROID_UPDATE_MINIMUM_SUPPORTED_VERSION_CODE = 5
    with pytest.raises(ImproperlyConfigured, match="version codes"):
        AndroidUpdateService.latest_release()
