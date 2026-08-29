from django.urls import path

from apps.tasks.views import (
    CompleteTaskView,
    TaskDetailView,
    TaskExecutionSignalListCreateView,
    TaskExecutionSummaryView,
    TaskListCreateView,
)

urlpatterns = [
    path("", TaskListCreateView.as_view(), name="task-list-create"),
    path("<uuid:task_id>/", TaskDetailView.as_view(), name="task-detail"),
    path("<uuid:task_id>/complete/", CompleteTaskView.as_view(), name="task-complete"),
    path(
        "<uuid:task_id>/execution-signals/",
        TaskExecutionSignalListCreateView.as_view(),
        name="task-execution-signals",
    ),
    path(
        "<uuid:task_id>/execution-summary/",
        TaskExecutionSummaryView.as_view(),
        name="task-execution-summary",
    ),
]
