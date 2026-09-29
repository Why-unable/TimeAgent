from langchain.tools import ToolRuntime, tool

from apps.agents.context import RuntimeContext
from common.time import to_user_timezone


@tool
def get_current_datetime(runtime: ToolRuntime[RuntimeContext]) -> dict[str, str]:
    """Return the run anchor in UTC and user-local time plus the trusted server clock.

    Use run_anchor_datetime_local for schedule decisions and relative dates so wall-clock
    constraints are unambiguous. Use observed time only when the user explicitly needs the
    current clock time.
    """

    context = runtime.context
    observed_datetime = context.observed_datetime()
    return {
        "run_anchor_datetime_utc": context.current_datetime.isoformat(),
        "run_anchor_datetime_local": to_user_timezone(
            context.current_datetime, context.timezone
        ).isoformat(),
        "observed_datetime_utc": observed_datetime.isoformat(),
        "observed_datetime_local": to_user_timezone(
            observed_datetime, context.timezone
        ).isoformat(),
        "timezone": context.timezone,
        "locale": context.locale,
    }


TIME_TOOLS = [get_current_datetime]
