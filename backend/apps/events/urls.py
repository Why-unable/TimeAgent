from django.urls import path

from apps.events.views import CalendarEventDetailView, CalendarEventListCreateView

urlpatterns = [
    path("", CalendarEventListCreateView.as_view(), name="event-list-create"),
    path("<uuid:event_id>/", CalendarEventDetailView.as_view(), name="event-detail"),
]
