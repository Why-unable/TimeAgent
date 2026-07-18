from django.urls import path

from apps.conversations.views import (
    AgentRunCancelView,
    AgentRunDetailView,
    AgentRunEventStreamView,
    ChatMessageView,
    ConversationDetailView,
    ConversationListCreateView,
)

urlpatterns = [
    path("conversations/", ConversationListCreateView.as_view(), name="conversation-list-create"),
    path(
        "conversations/<uuid:conversation_id>/",
        ConversationDetailView.as_view(),
        name="conversation-detail",
    ),
    path("messages/", ChatMessageView.as_view(), name="chat-message"),
    path("runs/<uuid:run_id>/", AgentRunDetailView.as_view(), name="agent-run-detail"),
    path("runs/<uuid:run_id>/cancel/", AgentRunCancelView.as_view(), name="agent-run-cancel"),
    path("runs/<uuid:run_id>/events/", AgentRunEventStreamView.as_view(), name="agent-run-events"),
]
