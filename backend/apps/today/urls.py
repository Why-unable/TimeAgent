from django.urls import path

from apps.today.views import TodaySummaryView

urlpatterns = [
    path("", TodaySummaryView.as_view(), name="today-summary"),
]
