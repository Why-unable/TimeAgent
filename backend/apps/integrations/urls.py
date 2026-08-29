from django.urls import path

from apps.integrations.views import (
    CalendarSyncConnectionListView,
    CalendarSyncRunView,
    GoogleCalendarDisconnectView,
    GoogleCalendarOAuthCallbackView,
    GoogleCalendarOAuthStartView,
)

urlpatterns = [
    path(
        "calendar/connections/",
        CalendarSyncConnectionListView.as_view(),
        name="calendar-sync-connections",
    ),
    path(
        "calendar/connections/<uuid:connection_id>/sync/",
        CalendarSyncRunView.as_view(),
        name="calendar-sync-run",
    ),
    path(
        "calendar/connections/<uuid:connection_id>/disconnect/",
        GoogleCalendarDisconnectView.as_view(),
        name="google-calendar-disconnect",
    ),
    path(
        "calendar/oauth/google/start/",
        GoogleCalendarOAuthStartView.as_view(),
        name="google-calendar-oauth-start",
    ),
    path(
        "calendar/oauth/google/callback/",
        GoogleCalendarOAuthCallbackView.as_view(),
        name="google-calendar-oauth-callback",
    ),
]
