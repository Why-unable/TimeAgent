from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

from apps.health.views import live, ready

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live", live, name="health-live"),
    path("health/ready", ready, name="health-ready"),
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("api/v1/preferences/", include("apps.preferences.urls")),
]
