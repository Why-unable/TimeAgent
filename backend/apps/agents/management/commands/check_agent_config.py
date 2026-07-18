from django.core.management.base import BaseCommand

from apps.agents.configuration import default_config_path, get_agent_config


class Command(BaseCommand):
    help = "Validate Agent YAML configuration without displaying secrets"

    def handle(self, *args: object, **options: object) -> None:
        del args, options
        config = get_agent_config()
        model = config.selected_model()
        self.stdout.write(
            self.style.SUCCESS(
                "Agent config is valid: "
                f"path={default_config_path()}, "
                f"model_alias={config.agent.default_model}, "
                f"provider={model.provider}, model={model.model}"
            )
        )
