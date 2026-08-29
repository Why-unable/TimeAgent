import json

from django.core.management.base import BaseCommand

from apps.planning.adaptive_benchmark import run_adaptive_stability_benchmark


class Command(BaseCommand):
    help = "Compare bounded local replan stability with a full-compaction baseline."

    def handle(self, *args: object, **options: object) -> None:
        self.stdout.write(
            json.dumps(run_adaptive_stability_benchmark(), ensure_ascii=False, sort_keys=True)
        )
