from django.core.checks import run_checks
from django.test import override_settings


def test_adaptive_dispatch_configuration_check_rejects_unsafe_bounds() -> None:
    with override_settings(
        ADAPTIVE_REPLAN_DISPATCH_INTERVAL_SECONDS=1,
        ADAPTIVE_REPLAN_HORIZON_HOURS=1000,
    ):
        errors = [error for error in run_checks() if error.id == "planning.E001"]

    assert len(errors) == 2
