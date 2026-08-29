from django.conf import settings
from django.core.checks import Error, register


@register()
def check_adaptive_replan_dispatch_configuration(**kwargs: object) -> list[Error]:
    del kwargs
    bounds = {
        "ADAPTIVE_REPLAN_DISPATCH_INTERVAL_SECONDS": (
            settings.ADAPTIVE_REPLAN_DISPATCH_INTERVAL_SECONDS,
            30,
            86400,
        ),
        "ADAPTIVE_REPLAN_HORIZON_HOURS": (
            settings.ADAPTIVE_REPLAN_HORIZON_HOURS,
            1,
            168,
        ),
    }
    errors: list[Error] = []
    for name, (value, minimum, maximum) in bounds.items():
        if not minimum <= value <= maximum:
            errors.append(
                Error(
                    f"{name} must be between {minimum} and {maximum}",
                    id="planning.E001",
                )
            )
    return errors
