from django.urls import path

from apps.time_memory.capacity_views import CapacityForecastView
from apps.time_memory.views import (
    CurrentTimeMemoryView,
    DecisionProfileView,
    DurationRecommendationView,
    MemoryProposalDecisionView,
    MemoryProposalListView,
    MemoryProposalUndoView,
    RecentMemoryProposalListView,
    SemanticMemoryListView,
    TimeMemoryPatternView,
    TimeMemoryPlaceView,
)

urlpatterns = [
    path("me/capacity-forecast/", CapacityForecastView.as_view(), name="capacity-forecast"),
    path("me/", CurrentTimeMemoryView.as_view(), name="current-time-memory"),
    path("me/semantic/", SemanticMemoryListView.as_view(), name="semantic-memory-list"),
    path("me/proposals/", MemoryProposalListView.as_view(), name="memory-proposal-list"),
    path(
        "me/proposals/recent/",
        RecentMemoryProposalListView.as_view(),
        name="recent-memory-proposal-list",
    ),
    path(
        "me/proposals/<uuid:proposal_id>/decision/",
        MemoryProposalDecisionView.as_view(),
        name="memory-proposal-decision",
    ),
    path(
        "me/proposals/<uuid:proposal_id>/undo/",
        MemoryProposalUndoView.as_view(),
        name="memory-proposal-undo",
    ),
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
