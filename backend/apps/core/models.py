"""Modèles transverses : journal d'audit."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Entrée d'audit persistante pour les actions sensibles."""

    class Action(models.TextChoices):
        CREATE = "create", "Création"
        UPDATE = "update", "Modification"
        DELETE = "delete", "Suppression"
        LOGIN = "login", "Connexion"
        LOGOUT = "logout", "Déconnexion"
        SUSPEND = "suspend", "Suspension"
        RESTORE = "restore", "Restauration"
        SYSTEM = "system", "Système"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    resource_type = models.CharField(max_length=64)
    resource_id = models.CharField(max_length=64, blank=True, default="")
    message = models.TextField(blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    request_id = models.CharField(max_length=64, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["resource_type", "resource_id"]),
            models.Index(fields=["action", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.resource_type}:{self.resource_id}"
