from django.apps import AppConfig


class ObservabilityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.observability"

    def ready(self) -> None:
        from apps.observability.metrics import register_business_collector

        register_business_collector()
