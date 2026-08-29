import json
from argparse import ArgumentParser
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.time_memory.benchmark import benchmark_duration_profile


class Command(BaseCommand):
    help = "Evaluate duration calibration against fixed and user-estimate baselines."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--user-id", type=int, required=True)
        parser.add_argument("--min-samples", type=int, default=10)

    def handle(self, *args: object, **options: Any) -> None:
        user = get_user_model().objects.get(pk=options["user_id"])
        result = benchmark_duration_profile(user=user, min_samples=options["min_samples"])
        self.stdout.write(json.dumps(result.as_dict(), ensure_ascii=False, sort_keys=True))
