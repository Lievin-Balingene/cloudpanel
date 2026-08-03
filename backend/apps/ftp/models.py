"""Modèles comptes FTP et journaux."""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class FtpAccount(models.Model):
    """Compte FTP virtuel rattaché à un utilisateur d'hébergement."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ftp_accounts",
    )
    username = models.CharField(max_length=64, unique=True, db_index=True)
    password_hash = models.CharField(max_length=256)
    directory = models.CharField(
        max_length=512,
        help_text="Chemin absolu du home FTP (jail).",
    )
    relative_directory = models.CharField(
        max_length=512,
        blank=True,
        default="public_html",
        help_text="Chemin relatif au home du compte propriétaire.",
    )
    quota_mb = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="0 = hérité / illimité selon package.",
    )
    bandwidth_kbs = models.PositiveIntegerField(
        default=0,
        help_text="Limite bande passante Ko/s (0 = illimitée).",
    )
    is_active = models.BooleanField(default=True)
    is_suspended = models.BooleanField(default=False)
    can_write = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True, default="")
    last_login_at = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("username",)
        indexes = [
            models.Index(fields=["owner", "is_active"]),
            models.Index(fields=["is_suspended"]),
        ]

    def __str__(self) -> str:
        return self.username

    def set_password(self, raw_password: str) -> None:
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password(raw_password, self.password_hash)

    @property
    def status(self) -> str:
        if self.is_suspended:
            return "suspended"
        if not self.is_active:
            return "inactive"
        return "active"


class FtpLog(models.Model):
    """Journal d'événements FTP."""

    class EventType(models.TextChoices):
        LOGIN = "login", "Connexion"
        LOGOUT = "logout", "Déconnexion"
        LOGIN_FAILED = "login_failed", "Échec connexion"
        UPLOAD = "upload", "Upload"
        DOWNLOAD = "download", "Download"
        DELETE = "delete", "Suppression"
        MKDIR = "mkdir", "Création dossier"
        RENAME = "rename", "Renommage"
        SYSTEM = "system", "Système"

    account = models.ForeignKey(
        FtpAccount,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="logs",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ftp_logs",
        null=True,
        blank=True,
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices, db_index=True)
    username = models.CharField(max_length=64, blank=True, default="")
    path = models.CharField(max_length=1024, blank=True, default="")
    bytes_transferred = models.BigIntegerField(default=0)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    message = models.TextField(blank=True, default="")
    success = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["username", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} {self.username} @ {self.created_at.isoformat()}"
