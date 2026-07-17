from django.urls import path

from apps.tasks.views import CompleteTaskView, TaskDetailView, TaskListCreateView

urlpatterns = [
    path("", TaskListCreateView.as_view(), name="task-list-create"),
    path("<uuid:task_id>/", TaskDetailView.as_view(), name="task-detail"),
    path("<uuid:task_id>/complete/", CompleteTaskView.as_view(), name="task-complete"),
]
