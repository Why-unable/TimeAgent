import os
from pathlib import Path

from corsheaders.defaults import default_headers

BASE_DIR = Path(__file__).resolve().parents[2]

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-development-only-key")
DEBUG = False
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]
# Capacitor's Android WebView is served from https://localhost.  It is a
# cross-origin client of the public backend, so Django must accept that origin
# for CSRF-protected unauthenticated flows such as registration and password
# reset.  Keep browser deployments configurable through the environment.
CSRF_TRUSTED_ORIGINS = list(
    dict.fromkeys(
        [
            "https://localhost",
            *[
                origin.strip()
                for origin in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
                if origin.strip()
            ],
        ]
    )
)
# The native Android (Capacitor) WebView loads bundled assets from
# https://localhost, so its API calls to the public backend are cross-origin.
# The web client is same-origin and never triggers CORS. Defaults cover the
# Capacitor WebView origins; override via DJANGO_CORS_ALLOWED_ORIGINS if needed.
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "DJANGO_CORS_ALLOWED_ORIGINS",
        "https://localhost,capacitor://localhost",
    ).split(",")
    if origin.strip()
]
# Custom request headers the clients send that are not CORS-safelisted, so a
# cross-origin preflight would otherwise reject them:
#  - x-request-id: sent on every apiRequest call for tracing.
#  - last-event-id: sent by the chat SSE stream (sse-client.ts) to resume from a
#    cursor; without it the stream's preflight fails as "Failed to fetch".
CORS_ALLOW_HEADERS = (*default_headers, "x-request-id", "last-event-id")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_prometheus",
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "apps.accounts",
    "apps.action_proposals",
    "apps.agents",
    "apps.briefings",
    "apps.conversations",
    "apps.health",
    "apps.notifications",
    "apps.preferences",
    "apps.reminders",
    "apps.events",
    "apps.external_data",
    "apps.tasks",
    "apps.planning",
    "apps.today",
]

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # CorsMiddleware must run before CommonMiddleware so preflight/actual
    # responses carry CORS headers. The native Android (Capacitor) WebView is
    # served from https://localhost, making its API calls cross-origin (ADR-0009).
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "config.observability.RequestContextMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "time_agent"),
        "USER": os.getenv("POSTGRES_USER", "time_agent"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "time_agent"),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

LANGGRAPH_DATABASE_URL = os.getenv("LANGGRAPH_DATABASE_URL", "")
LANGGRAPH_DATABASE_ALIAS = os.getenv("LANGGRAPH_DATABASE_ALIAS", "default")
LANGGRAPH_POSTGRES_CONNECT_TIMEOUT = int(os.getenv("LANGGRAPH_POSTGRES_CONNECT_TIMEOUT", "10"))
LANGGRAPH_STORE_POOL_MIN_SIZE = int(os.getenv("LANGGRAPH_STORE_POOL_MIN_SIZE", "1"))
LANGGRAPH_STORE_POOL_MAX_SIZE = int(os.getenv("LANGGRAPH_STORE_POOL_MAX_SIZE", "10"))

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = os.getenv("DEFAULT_LOCALE", "zh-hans")
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_USER_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Asia/Shanghai")
DEFAULT_USER_LOCALE = os.getenv("DEFAULT_LOCALE", "zh-CN")
ACTION_PROPOSAL_TTL_SECONDS = int(os.getenv("ACTION_PROPOSAL_TTL_SECONDS", "86400"))
AUTH_REGISTRATION_ENABLED = os.getenv("AUTH_REGISTRATION_ENABLED", "true").lower() == "true"
NOTIFICATION_MAX_RETRIES = int(os.getenv("NOTIFICATION_MAX_RETRIES", "4"))
NOTIFICATION_DEFAULT_CHANNEL = os.getenv("NOTIFICATION_DEFAULT_CHANNEL", "console")
NOTIFICATION_SENDING_STALE_SECONDS = int(os.getenv("NOTIFICATION_SENDING_STALE_SECONDS", "300"))
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.getenv("EMAIL_USERNAME", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "false").lower() == "true"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "false").lower() == "true"
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT_SECONDS", "10"))
EMAIL_FROM_ADDRESS = os.getenv("EMAIL_FROM_ADDRESS", "Time Agent <noreply@localhost>")
WEB_PUSH_VAPID_PUBLIC_KEY = os.getenv("WEB_PUSH_VAPID_PUBLIC_KEY", "")
WEB_PUSH_VAPID_PRIVATE_KEY = os.getenv("WEB_PUSH_VAPID_PRIVATE_KEY", "")
WEB_PUSH_VAPID_SUBJECT = os.getenv("WEB_PUSH_VAPID_SUBJECT", "")
WEB_PUSH_TIMEOUT_SECONDS = int(os.getenv("WEB_PUSH_TIMEOUT_SECONDS", "10"))

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    # Token auth is listed first so an unauthenticated request yields 401 (its
    # authenticate_header sets WWW-Authenticate) rather than 403 — DRF derives
    # the status from the FIRST authenticator's header. 403 would read as
    # "service error" to clients that only treat 401 as "signed out". Session
    # auth still keeps the same-origin web client working unchanged (ADR-0009);
    # token auth is the additive channel for the native Android (Capacitor) app,
    # whose WebView origin is cross-origin and cannot rely on session cookies.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_THROTTLE_RATES": {"authentication": "10/min"},
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Time Agent API",
    "DESCRIPTION": "Time Agent backend contract",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "ENUM_NAME_OVERRIDES": {
        "DependencyStatusEnum": "apps.health.serializers.DependencyStatus",
        "CalendarEventStatusEnum": "apps.events.models.CalendarEventStatus",
        "TaskStatusEnum": "apps.tasks.models.TaskStatus",
        "ReminderStatusEnum": "apps.reminders.models.ReminderStatus",
        "ActionProposalStatusEnum": "apps.action_proposals.models.ActionProposalStatus",
        "RiskLevelEnum": "apps.action_proposals.models.RiskLevel",
        "ConversationKindEnum": "apps.conversations.models.ConversationKind",
        "NotificationSourceTypeEnum": "apps.notifications.models.NotificationSourceType",
        "NotificationChannelTypeEnum": "apps.notifications.models.NotificationChannelType",
    },
}

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    "dispatch-due-reminders": {
        "task": "reminders.dispatch_due",
        "schedule": 30.0,
    },
    "expire-action-proposals": {
        "task": "action_proposals.expire_due",
        "schedule": 60.0,
    },
    "dispatch-due-notifications": {
        "task": "notifications.dispatch_due",
        "schedule": 30.0,
    },
    "schedule-daily-briefings": {
        "task": "briefings.schedule_due",
        "schedule": 60.0,
    },
}

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": (
                '{{"time":"{asctime}","level":"{levelname}",'
                '"logger":"{name}","message":"{message}",'
                '"request_id":"{request_id}","method":"{method}",'
                '"path":"{path}","status_code":"{status_code}",'
                '"duration_ms":"{duration_ms}"}}'
            ),
            "style": "{",
            "defaults": {
                "request_id": "-",
                "method": "-",
                "path": "-",
                "status_code": "-",
                "duration_ms": "-",
            },
        }
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
}
