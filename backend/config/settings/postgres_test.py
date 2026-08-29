import os

from config.settings.test import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "time_agent_test"),
        "USER": os.getenv("POSTGRES_USER", "time_agent"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "time_agent"),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 0,
    }
}
