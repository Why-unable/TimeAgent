from typing import Any

from django.core.checks import Error, Tags, register
from django.core.exceptions import ImproperlyConfigured

from apps.agents.configuration import get_agent_config


@register(Tags.compatibility)
def check_agent_configuration(**kwargs: Any) -> list[Error]:
    del kwargs
    try:
        get_agent_config()
    except ImproperlyConfigured as exc:
        return [
            Error(
                str(exc),
                hint="Fix TIME_AGENT_CONFIG_PATH or the referenced Agent YAML file.",
                id="agents.E001",
            )
        ]
    return []
