from __future__ import annotations

from django.urls import path

from apps.ai_assistant.views import (
    AiPlaybooksView,
    AiStatusView,
    ConfirmActionView,
    ConversationDetailView,
    ConversationListCreateView,
    ConversationMessageView,
)

urlpatterns = [
    path("status/", AiStatusView.as_view(), name="ai-status"),
    path("playbooks/", AiPlaybooksView.as_view(), name="ai-playbooks"),
    path("conversations/", ConversationListCreateView.as_view(), name="ai-conversation-list"),
    path(
        "conversations/<int:pk>/",
        ConversationDetailView.as_view(),
        name="ai-conversation-detail",
    ),
    path(
        "conversations/<int:pk>/messages/",
        ConversationMessageView.as_view(),
        name="ai-conversation-message",
    ),
    path("actions/confirm/", ConfirmActionView.as_view(), name="ai-action-confirm"),
]
