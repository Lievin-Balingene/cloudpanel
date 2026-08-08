from __future__ import annotations

from django.contrib import admin

from apps.ai_assistant.models import AgentActionLog, Conversation, Message, PendingAction


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "title", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("title", "owner__username")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "role", "tool_name", "created_at")
    list_filter = ("role",)


@admin.register(PendingAction)
class PendingActionAdmin(admin.ModelAdmin):
    list_display = ("token", "owner", "tool_name", "status", "expires_at", "created_at")
    list_filter = ("status", "tool_name")


@admin.register(AgentActionLog)
class AgentActionLogAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "tool_name", "success", "confirmed", "created_at")
    list_filter = ("tool_name", "success")
