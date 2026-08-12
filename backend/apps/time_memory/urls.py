from django.urls import path

from apps.time_memory.views import (
    CurrentTimeMemoryView,
    TimeMemoryPatternView,
    TimeMemoryPlaceView,
)

urlpatterns = [
    path("me/", CurrentTimeMemoryView.as_view(), name="current-time-memory"),
    path("me/places/<str:place_id>/", TimeMemoryPlaceView.as_view(), name="time-memory-place"),
    path(
        "me/patterns/<str:pattern_id>/",
        TimeMemoryPatternView.as_view(),
        name="time-memory-pattern",
    ),
]
