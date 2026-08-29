from config.settings.base import *  # noqa: F403

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
EMAIL_FROM_ADDRESS = "Time Agent Tests <time-agent@example.test>"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
AGENT_EVENT_STREAM_ENABLED = False
TIME_MEMORY_AUTO_REFRESH_ENABLED = False
CALENDAR_OAUTH_FERNET_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
GOOGLE_CALENDAR_CLIENT_ID = "test-google-client"
GOOGLE_CALENDAR_CLIENT_SECRET = "test-google-secret"
GOOGLE_CALENDAR_REDIRECT_URI = "https://testserver/api/v1/integrations/calendar/oauth/google/callback/"
