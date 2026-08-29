import json
from argparse import ArgumentParser
from datetime import datetime
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.insights.evaluation import InsightEvaluationService


class Command(BaseCommand):
    help = "Evaluate proactive-insight outcomes over an explicit observation window."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--user-id", type=int, required=True)
        parser.add_argument("--window-start", required=True)
        parser.add_argument("--window-end", required=True)
        parser.add_argument("--max-dismiss-rate", type=float)
        parser.add_argument("--max-delivery-failure-rate", type=float)
        parser.add_argument("--max-false-positive-rate", type=float)

    def handle(self, *args: object, **options: Any) -> None:
        try:
            start = datetime.fromisoformat(options["window_start"])
            end = datetime.fromisoformat(options["window_end"])
        except ValueError as exc:
            raise CommandError("window values must be ISO-8601 datetimes") from exc
        user = get_user_model().objects.get(pk=options["user_id"])
        try:
            report = InsightEvaluationService.report(
                user=user,
                window_start=start,
                window_end=end,
                max_dismiss_rate=options["max_dismiss_rate"],
                max_delivery_failure_rate=options["max_delivery_failure_rate"],
                max_false_positive_rate=options["max_false_positive_rate"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
