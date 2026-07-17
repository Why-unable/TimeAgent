import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-development-only-key")
DEBUG = False
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "apps.agents",
    "apps.health",
    "apps.preferences",
    "apps.reminders",
    "apps.events",
    "apps.tasks",
    "apps.planning",
    "apps.today",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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
LANGGRAPH_POSTGRES_CONNECT_TIMEOUT = int(
    os.getenv("LANGGRAPH_POSTGRES_CONNECT_TIMEOUT", "10")
)
LANGGRAPH_STORE_POOL_MIN_SIZE = int(os.getenv("LANGGRAPH_STORE_POOL_MIN_SIZE", "1"))
LANGGRAPH_STORE_POOL_MAX_SIZE = int(os.getenv("LANGGRAPH_STORE_POOL_MAX_SIZE", "10"))
LANGGRAPH_RECURSION_LIMIT = int(os.getenv("LANGGRAPH_RECURSION_LIMIT", "50"))
LANGGRAPH_MAX_CONCURRENCY = int(os.getenv("LANGGRAPH_MAX_CONCURRENCY", "4"))

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

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
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
    },
}

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    "dispatch-due-reminders": {
        "task": "reminders.dispatch_due",
        "schedule": 30.0,
    }
}

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": (
                '{{"time":"{asctime}","level":"{levelname}",'
                '"logger":"{name}","message":"{message}"}}'
            ),
            "style": "{",
        }
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
}
