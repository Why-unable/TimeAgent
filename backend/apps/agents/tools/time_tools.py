from langchain.tools import ToolRuntime, tool

from apps.agents.context import RuntimeContext


@tool
def get_current_datetime(runtime: ToolRuntime[RuntimeContext]) -> dict[str, str]:
    """Return the trusted current UTC instant and the user's IANA timezone and locale."""

    context = runtime.context
    return {
        "current_datetime_utc": context.current_datetime.isoformat(),
        "timezone": context.timezone,
        "locale": context.locale,
    }


TIME_TOOLS = [get_current_datetime]
