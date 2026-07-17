from django.core.management.base import BaseCommand

from apps.agents.memory.persistence import setup_langgraph_persistence


class Command(BaseCommand):
    help = "Create or migrate PostgreSQL tables managed by LangGraph"

    def handle(self, *args: object, **options: object) -> None:
        setup_langgraph_persistence()
        self.stdout.write(self.style.SUCCESS("LangGraph persistence is ready."))
