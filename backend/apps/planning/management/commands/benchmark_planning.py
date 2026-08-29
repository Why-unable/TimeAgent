import json

from django.core.management.base import BaseCommand

from apps.planning.benchmark import run_default_benchmark


class Command(BaseCommand):
    help = "Run the deterministic planning baseline benchmark and print JSON."

    def handle(self, *args: object, **options: object) -> None:
        self.stdout.write(json.dumps(run_default_benchmark(), ensure_ascii=False, sort_keys=True))
