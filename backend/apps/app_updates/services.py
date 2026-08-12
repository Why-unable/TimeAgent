from dataclasses import dataclass
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.dateparse import parse_datetime

MAX_ANDROID_APK_BYTES = 250 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class AndroidRelease:
    version_code: int
    version_name: str
    download_url: str
    sha256: str
    size_bytes: int
    release_notes: str
    published_at: str
    minimum_supported_version_code: int


class AndroidUpdateService:
    @staticmethod
    def latest_release() -> AndroidRelease | None:
        if not settings.ANDROID_UPDATE_ENABLED:
            return None
        download_url = settings.ANDROID_UPDATE_DOWNLOAD_URL.strip()
        parsed = urlparse(download_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ImproperlyConfigured("ANDROID_UPDATE_DOWNLOAD_URL must be an absolute HTTPS URL")
        sha256 = settings.ANDROID_UPDATE_SHA256.strip().lower()
        if len(sha256) != 64 or any(character not in "0123456789abcdef" for character in sha256):
            raise ImproperlyConfigured(
                "ANDROID_UPDATE_SHA256 must be a 64-character hexadecimal digest"
            )
        version_code = settings.ANDROID_UPDATE_VERSION_CODE
        minimum_version = settings.ANDROID_UPDATE_MINIMUM_SUPPORTED_VERSION_CODE
        if version_code < 1 or minimum_version < 1 or minimum_version > version_code:
            raise ImproperlyConfigured("Android update version codes are invalid")
        version_name = settings.ANDROID_UPDATE_VERSION_NAME.strip()
        if not version_name:
            raise ImproperlyConfigured("ANDROID_UPDATE_VERSION_NAME must not be blank")
        size_bytes = settings.ANDROID_UPDATE_SIZE_BYTES
        if not 1 <= size_bytes <= MAX_ANDROID_APK_BYTES:
            raise ImproperlyConfigured("ANDROID_UPDATE_SIZE_BYTES is outside the allowed range")
        published_at = settings.ANDROID_UPDATE_PUBLISHED_AT.strip()
        parsed_published_at = parse_datetime(published_at)
        if parsed_published_at is None or parsed_published_at.tzinfo is None:
            raise ImproperlyConfigured("ANDROID_UPDATE_PUBLISHED_AT must include a UTC offset")
        return AndroidRelease(
            version_code=version_code,
            version_name=version_name,
            download_url=download_url,
            sha256=sha256,
            size_bytes=size_bytes,
            release_notes=settings.ANDROID_UPDATE_RELEASE_NOTES.strip(),
            published_at=published_at,
            minimum_supported_version_code=minimum_version,
        )
