from django.urls import path

from apps.time_memory.capacity_views import CapacityForecastView
from apps.time_memory.views import (
    CurrentTimeMemoryView,
    DecisionProfileView,
    DurationRecommendationView,
    TimeMemoryPatternView,
    TimeMemoryPlaceView,
)

urlpatterns = [
    path("me/capacity-forecast/", CapacityForecastView.as_view(), name="capacity-forecast"),
    path("me/", CurrentTimeMemoryView.as_view(), name="current-time-memory"),
    path("me/decision-profile/", DecisionProfileView.as_view(), name="decision-profile"),
    path(
        "me/duration-recommendations/<uuid:task_id>/",
        DurationRecommendationView.as_view(),
        name="duration-recommendation",
    ),
    path("me/places/<str:place_id>/", TimeMemoryPlaceView.as_view(), name="time-memory-place"),
    path(
        "me/patterns/<str:pattern_id>/",
        TimeMemoryPatternView.as_view(),
        name="time-memory-pattern",
    ),
]
