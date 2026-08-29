import json
import os
import time
from argparse import ArgumentParser, ArgumentTypeError
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import connection as database_connection
from django.utils.dateparse import parse_datetime

from apps.integrations.calendar.verification import GoogleCalendarVerificationService
from apps.integrations.models import CalendarSyncConnection
from common.time import to_utc


def _aware_datetime(value: str) -> datetime:
    parsed = parse_datetime(value)
    if parsed is None:
        raise ArgumentTypeError("Expected an ISO-8601 datetime")
    try:
        return to_utc(parsed)
    except ValueError as exc:
        raise ArgumentTypeError("Datetime must include an explicit UTC offset") from exc


class Command(BaseCommand):
    help = "Run a sanitized live Google Calendar verification and emit JSON evidence."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--user-id", type=int, required=True)
        parser.add_argument("--connection-id", type=UUID, required=True)
        parser.add_argument("--starts-at", type=_aware_datetime, required=True)
        parser.add_argument("--starts-before", type=_aware_datetime, required=True)
        parser.add_argument("--output", default="")
        parser.add_argument("--force", action="store_true")

    def handle(self, *args: object, **options: Any) -> None:
        del args
        output_path = str(options["output"]).strip()
        destination = Path(output_path).expanduser() if output_path else None
        if destination is not None and destination.exists() and not options["force"]:
            raise CommandError("Output file already exists; pass --force to replace it")
        try:
            user = User.objects.get(pk=options["user_id"])
        except User.DoesNotExist as exc:
            raise CommandError("Verification user does not exist") from exc

        try:
            report = GoogleCalendarVerificationService.verify(
                user=user,
                connection_id=options["connection_id"],
                starts_at=options["starts_at"],
                starts_before=options["starts_before"],
                monotonic=time.perf_counter,
            )
        except CalendarSyncConnection.DoesNotExist as exc:
            raise CommandError("Google Calendar connection does not exist") from exc
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        payload = {
            **report.as_dict(),
            "database_vendor": database_connection.vendor,
            "git_commit": os.getenv("GIT_COMMIT_SHA", "unknown"),
        }
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        if destination is not None:
            destination.write_text(f"{serialized}\n", encoding="utf-8")
            destination.chmod(0o600)
            self.stdout.write(f"Wrote sanitized report to {destination}")
        else:
            self.stdout.write(serialized)

        if report.status != "pass":
            raise CommandError("Google Calendar verification failed; inspect the report")
