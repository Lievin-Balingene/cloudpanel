"""Modèles sécurité panel (lockout, IP, politique MDP)."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class SecurityPolicy(models.Model):
    """Politique globale (une seule ligne active attendue)."""

    class IpMode(models.TextChoices):
        OFF = "off", "Désactivé"
        ALLOWLIST = "allowlist", "Allowlist seule"
        BLOCKLIST = "blocklist", "Blocklist"

    password_min_length = models.PositiveSmallIntegerField(default=10)
    require_uppercase = models.BooleanField(default=False)
    require_digit = models.BooleanField(default=True)
    require_special = models.BooleanField(default=False)
    lockout_max_attempts = models.PositiveSmallIntegerField(default=5)
    lockout_window_minutes = models.PositiveSmallIntegerField(default=15)
    lockout_duration_minutes = models.PositiveSmallIntegerField(default=30)
    ip_mode = models.CharField(
        max_length=16,
        choices=IpMode.choices,
        default=IpMode.OFF,
    )
    force_2fa_admins = models.BooleanField(
        default=False,
        help_text="Exige 2FA pour administrateurs et revendeurs.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Politique de sécurité"
        verbose_name_plural = "Politiques de sécurité"

    def __str__(self) -> str:
        return f"SecurityPolicy(ip={self.ip_mode})"


class IpAccessRule(models.Model):
    class ListType(models.TextChoices):
        ALLOW = "allow", "Allow"
        BLOCK = "block", "Block"

    cidr = models.CharField(max_length=64)
    list_type = models.CharField(max_length=8, choices=ListType.choices)
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ip_access_rules_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("list_type", "cidr")
        indexes = [models.Index(fields=["list_type", "is_active"])]

    def __str__(self) -> str:
        return f"{self.list_type}:{self.cidr}"


class LoginAttempt(models.Model):
    email = models.EmailField(blank=True, default="", db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    success = models.BooleanField(default=False)
    message = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.email}:{self.success}"


class AccountLockout(models.Model):
    """Verrouillage temporaire par clé (email ou ip:...)."""

    key = models.CharField(max_length=255, unique=True, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self) -> str:
        return self.key
