from pathlib import Path

from config.settings.base import BASE_DIR
from config.settings.test import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(BASE_DIR) / "evaluation_reports" / "harness-hardening-v2.sqlite3",
    }
}
