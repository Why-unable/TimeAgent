from django.urls import path

from apps.insights.views import (
    TemporalInsightActionView,
    TemporalInsightDetailView,
    TemporalInsightListView,
)

urlpatterns = [
    path("", TemporalInsightListView.as_view(), name="insight-list"),
    path("<uuid:insight_id>/", TemporalInsightDetailView.as_view(), name="insight-detail"),
    path("<uuid:insight_id>/action/", TemporalInsightActionView.as_view(), name="insight-action"),
]
