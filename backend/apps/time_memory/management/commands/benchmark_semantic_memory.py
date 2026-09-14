import json
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.time_memory.evaluation import GOLDEN_SET_PATH, run_semantic_memory_benchmark


class Command(BaseCommand):
    help = "Run the deterministic semantic-memory policy Golden Set benchmark."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--fixture", type=Path, default=GOLDEN_SET_PATH)
        parser.add_argument("--output", type=Path)

    def handle(self, *args: object, **options: Any) -> None:
        fixture = options["fixture"]
        try:
            report = run_semantic_memory_benchmark(fixture)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CommandError(f"unable to run semantic memory benchmark: {exc}") from exc
        rendered = json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        output = options.get("output")
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
        self.stdout.write(rendered)
