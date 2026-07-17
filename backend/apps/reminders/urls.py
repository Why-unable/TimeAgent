from django.urls import path

from apps.reminders.views import ReminderDestroyView, ReminderListCreateView

urlpatterns = [
    path("", ReminderListCreateView.as_view(), name="reminder-list-create"),
    path(
        "<uuid:reminder_id>/",
        ReminderDestroyView.as_view(),
        name="reminder-destroy",
    ),
]
