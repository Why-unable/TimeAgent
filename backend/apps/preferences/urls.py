from django.urls import path

from apps.preferences.views import CurrentUserPreferenceView

urlpatterns = [
    path("me/", CurrentUserPreferenceView.as_view(), name="current-user-preference"),
]
