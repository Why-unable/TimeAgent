from django.urls import path

from apps.app_updates.views import AndroidUpdateView

urlpatterns = [
    path("android/latest/", AndroidUpdateView.as_view(), name="android-update-latest"),
]
