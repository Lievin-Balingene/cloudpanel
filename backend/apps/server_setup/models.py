"""Modèle singleton de configuration serveur WHM."""
from __future__ import annotations

from django.db import models


class ServerSetup(models.Model):
    """Configuration globale hostname + nameservers (une seule ligne)."""

    hostname = models.CharField(max_length=255, blank=True, default="")
    nameserver1 = models.CharField(max_length=255, blank=True, default="")
    nameserver2 = models.CharField(max_length=255, blank=True, default="")
    nameserver3 = models.CharField(max_length=255, blank=True, default="")
    nameserver4 = models.CharField(max_length=255, blank=True, default="")
    resolver1 = models.GenericIPAddressField(null=True, blank=True)
    resolver2 = models.GenericIPAddressField(null=True, blank=True)
    contact_email = models.EmailField(blank=True, default="")
    apply_hostname_to_mail = models.BooleanField(default=True)
    last_hostname_error = models.TextField(blank=True, default="")
    hostname_applied_at = models.DateTimeField(null=True, blank=True)
    tweak_settings = models.JSONField(
        default=dict,
        blank=True,
        help_text="Tweak Settings WHM (catégories security, email, dns, …).",
    )
    extra_ips = models.JSONField(
        default=list,
        blank=True,
        help_text="Liste d'IP additionnelles du serveur (hors IP publique principale).",
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Configuration serveur"
        verbose_name_plural = "Configuration serveur"

    def __str__(self) -> str:
        return f"ServerSetup({self.hostname or 'unset'})"

    @classmethod
    def get_solo(cls) -> "ServerSetup":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
