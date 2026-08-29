from django.urls import path

from apps.briefings.views import (
    BriefingDefinitionDetailView,
    BriefingDefinitionListCreateView,
    BriefingRunDetailView,
    BriefingRunListLaunchView,
    EveningBriefingPreviewView,
)

urlpatterns = [
    path("evening-preview/", EveningBriefingPreviewView.as_view(), name="evening-briefing-preview"),
    path("definitions/", BriefingDefinitionListCreateView.as_view(), name="definition-list"),
    path(
        "definitions/<uuid:definition_id>/",
        BriefingDefinitionDetailView.as_view(),
        name="definition-detail",
    ),
    path("runs/", BriefingRunListLaunchView.as_view(), name="run-list-launch"),
    path("runs/<uuid:run_id>/", BriefingRunDetailView.as_view(), name="run-detail"),
]
