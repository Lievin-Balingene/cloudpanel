from __future__ import annotations

from rest_framework import serializers

from apps.ai_assistant.models import Conversation, Message, PendingAction


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = (
            "id",
            "role",
            "content",
            "tool_name",
            "tool_call_id",
            "metadata",
            "created_at",
        )


class ConversationSerializer(serializers.ModelSerializer):
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = (
            "id",
            "title",
            "status",
            "context",
            "message_count",
            "created_at",
            "updated_at",
        )

    def get_message_count(self, obj: Conversation) -> int:
        return obj.messages.count()


class ConversationDetailSerializer(ConversationSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta(ConversationSerializer.Meta):
        fields = ConversationSerializer.Meta.fields + ("messages",)


class SendMessageSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=8000)
    ui_context = serializers.DictField(required=False, allow_empty=True)
    auto = serializers.BooleanField(required=False, default=False)


class ConfirmActionSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=64)
    confirm = serializers.BooleanField()


class PendingActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PendingAction
        fields = (
            "token",
            "tool_name",
            "description",
            "params",
            "status",
            "expires_at",
            "created_at",
        )
