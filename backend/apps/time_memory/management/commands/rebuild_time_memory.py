from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.agents.memory.store import open_postgres_store
from apps.time_memory.updater import TimeMemoryUpdater


class Command(BaseCommand):
    help = "Rebuild deterministic Time Steward memory profiles"

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument("--user-id", help="Rebuild one user only")

    def handle(self, *args, **options) -> None:  # type: ignore[no-untyped-def]
        users = get_user_model().objects.all().order_by("pk")
        if options["user_id"]:
            users = users.filter(pk=options["user_id"])
            if not users.exists():
                raise CommandError("User does not exist")
        rebuilt = 0
        with open_postgres_store() as store:
            for user in users.iterator():
                if TimeMemoryUpdater.rebuild(user=user, store=store) is not None:
                    rebuilt += 1
        self.stdout.write(self.style.SUCCESS(f"Rebuilt {rebuilt} time memory profiles"))
