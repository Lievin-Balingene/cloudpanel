"""Services conversation AI."""
from __future__ import annotations

from apps.accounts.models import User
from apps.ai_assistant.models import Conversation
from apps.ai_assistant.services.agent import confirm_pending_action, run_assistant_turn
from apps.ai_assistant.services.context import build_user_context
from apps.ai_assistant.services.rate_limit import assert_ai_rate_limit


def conversations_qs(user: User):
    return Conversation.objects.filter(owner=user).exclude(status=Conversation.Status.ARCHIVED)


def create_conversation(user: User, *, title: str = "") -> Conversation:
    return Conversation.objects.create(
        owner=user,
        title=(title or "")[:160],
        context=build_user_context(user),
    )


def refresh_context(conversation: Conversation) -> Conversation:
    conversation.context = build_user_context(conversation.owner)
    conversation.save(update_fields=["context", "updated_at"])
    return conversation


def send_message(
    user: User,
    conversation: Conversation,
    text: str,
    *,
    ip_address: str | None = None,
) -> dict:
    if conversation.owner_id != user.pk and getattr(user, "role", None) != User.Role.ADMINISTRATOR:
        from apps.core.exceptions import VZoneAPIException

        raise VZoneAPIException(detail="Conversation interdite.", code="forbidden", status_code=403)
    assert_ai_rate_limit(int(user.pk))
    refresh_context(conversation)
    return run_assistant_turn(
        user=user,
        conversation=conversation,
        user_text=text,
        ip_address=ip_address,
    )


__all__ = [
    "conversations_qs",
    "create_conversation",
    "refresh_context",
    "send_message",
    "confirm_pending_action",
]
