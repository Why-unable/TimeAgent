from django.urls import path

from apps.interactions.views import (
    InteractionListCreateView,
    InteractionSubmitView,
    InteractionTelemetryView,
)

urlpatterns = [
    path("", InteractionListCreateView.as_view(), name="interaction-list-create"),
    path("telemetry/", InteractionTelemetryView.as_view(), name="interaction-telemetry"),
    path(
        "<uuid:interaction_id>/submit/", InteractionSubmitView.as_view(), name="interaction-submit"
    ),
]
