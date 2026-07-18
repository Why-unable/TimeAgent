from django.conf import settings
from langchain.tools import ToolRuntime, tool

from apps.agents.context import RuntimeContext
from apps.agents.tools.common import model_dict, require_actor
from apps.preferences.models import UserPreference
from apps.preferences.services import UserPreferenceService

PREFERENCE_FIELDS = (
    "timezone",
    "locale",
    "workday_start",
    "workday_end",
    "sleep_start",
    "sleep_end",
    "default_event_duration_minutes",
    "preferred_focus_periods",
    "default_reminder_offsets",
    "planning_rules",
)


@tool
def get_user_preferences(runtime: ToolRuntime[RuntimeContext]) -> dict[str, object]:
    """Read the current user's time and planning preferences without creating data."""

    actor = require_actor(runtime)
    preference = UserPreferenceService.get_for_user(actor)
    if preference is None:
        preference = UserPreference(
            user=actor,
            timezone=settings.DEFAULT_USER_TIMEZONE,
            locale=settings.DEFAULT_USER_LOCALE,
        )
    return model_dict(preference, PREFERENCE_FIELDS)


PREFERENCE_TOOLS = [get_user_preferences]
