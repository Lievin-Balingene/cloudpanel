"""Modèles conversation, actions en attente, journal agent."""
from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


class UserAiProviderSettings(models.Model):
    """BYOK : chaque client choisit son LLM (Ollama perso ou API OpenAI-compat)."""

    class Mode(models.TextChoices):
        SERVER = "server", "Serveur (défaut panel)"
        OLLAMA = "ollama", "Ollama (URL perso)"
        OPENAI_COMPAT = "openai_compat", "API OpenAI-compatible"

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_provider_settings",
    )
    mode = models.CharField(
        max_length=32,
        choices=Mode.choices,
        default=Mode.SERVER,
        db_index=True,
    )
    # URL publique du endpoint (ex. https://ollama.example.com ou https://api.openai.com/v1)
    base_url = models.CharField(max_length=512, blank=True, default="")
    # Clé API chiffrée Fernet (jamais renvoyée en clair)
    api_key_encrypted = models.TextField(blank=True, default="")
    model_name = models.CharField(max_length=128, blank=True, default="")
    enabled = models.BooleanField(default=True)
    last_test_ok = models.BooleanField(null=True, blank=True)
    last_test_message = models.CharField(max_length=255, blank=True, default="")
    last_tested_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI provider settings"
        verbose_name_plural = "AI provider settings"

    def __str__(self) -> str:
        return f"AI settings@{self.owner_id}:{self.mode}"

    @property
    def is_byok_active(self) -> bool:
        return bool(self.enabled and self.mode != self.Mode.SERVER and self.base_url.strip())


class Conversation(models.Model):
    """Fil de discussion assistant ↔ client."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archivée"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_conversations",
    )
    title = models.CharField(max_length=160, blank=True, default="")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    # Contexte déploiement (repo, runtime, domaine…) — jamais de secrets
    context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self) -> str:
        return self.title or f"Conversation #{self.pk}"


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"
        SYSTEM = "system", "System"
        TOOL = "tool", "Tool"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField(blank=True, default="")
    tool_name = models.CharField(max_length=64, blank=True, default="")
    tool_call_id = models.CharField(max_length=64, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("created_at",)


class PendingAction(models.Model):
    """Action d'écriture nécessitant confirmation explicite."""

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        CONFIRMED = "confirmed", "Confirmée"
        CANCELLED = "cancelled", "Annulée"
        EXECUTED = "executed", "Exécutée"
        FAILED = "failed", "Échouée"
        EXPIRED = "expired", "Expirée"

    token = models.CharField(max_length=64, unique=True, db_index=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_pending_actions",
    )
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="pending_actions",
        null=True,
        blank=True,
    )
    tool_name = models.CharField(max_length=64)
    params = models.JSONField(default=dict, blank=True)
    description = models.CharField(max_length=512, blank=True, default="")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    result = models.JSONField(default=dict, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    @staticmethod
    def new_token() -> str:
        return secrets.token_urlsafe(32)

    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at


class AgentActionLog(models.Model):
    """Journal de toutes les invocations d'outils (audit)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_action_logs",
    )
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="action_logs",
    )
    tool_name = models.CharField(max_length=64, db_index=True)
    params_redacted = models.JSONField(default=dict, blank=True)
    result_summary = models.TextField(blank=True, default="")
    success = models.BooleanField(default=True)
    requires_confirmation = models.BooleanField(default=False)
    confirmed = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
