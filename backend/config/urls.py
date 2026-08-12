from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

from apps.health.views import live, ready

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live", live, name="health-live"),
    path("health/ready", ready, name="health-ready"),
    path("", include("django_prometheus.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/preferences/", include("apps.preferences.urls")),
    path("api/v1/time-memory/", include("apps.time_memory.urls")),
    path("api/v1/reminders/", include("apps.reminders.urls")),
    path("api/v1/events/", include("apps.events.urls")),
    path("api/v1/tasks/", include("apps.tasks.urls")),
    path("api/v1/today/", include("apps.today.urls")),
    path("api/v1/chat/", include("apps.conversations.urls")),
    path("api/v1/action-proposals/", include("apps.action_proposals.urls")),
    path("api/v1/app-updates/", include("apps.app_updates.urls")),
    path("api/v1/briefings/", include("apps.briefings.urls")),
    path("api/v1/providers/", include("apps.external_data.urls")),
    path("api/v1/", include("apps.notifications.urls")),
]
