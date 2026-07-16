import os

from config.settings.base import *  # noqa: F403

DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
