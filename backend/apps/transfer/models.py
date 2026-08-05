"""Jobs de transfert de comptes (style WHM Transfer Tool)."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class TransferJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        RUNNING = "running", "En cours"
        COMPLETED = "completed", "Terminé"
        FAILED = "failed", "Échoué"
        CANCELLED = "cancelled", "Annulé"

    class SourceType(models.TextChoices):
        ARCHIVE = "archive", "Archive cPanel (pkgacct/cpmove)"
        REMOTE_WHM = "remote_whm", "Serveur WHM distant"

    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfer_jobs_started",
    )
    source_type = models.CharField(max_length=16, choices=SourceType.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)

    # Compte cible
    username = models.CharField(max_length=32, db_index=True)
    email = models.EmailField(blank=True, default="")
    password = models.CharField(max_length=128, blank=True, default="")
    package_name = models.CharField(max_length=64, blank=True, default="")
    overwrite = models.BooleanField(
        default=False,
        help_text="Si le compte existe déjà, écraser home / réimporter métadonnées.",
    )

    # Source archive
    archive_name = models.CharField(max_length=255, blank=True, default="")
    archive_path = models.CharField(max_length=1024, blank=True, default="")

    # Source remote WHM
    remote_host = models.CharField(max_length=255, blank=True, default="")
    remote_port = models.PositiveIntegerField(default=2087)
    remote_user = models.CharField(max_length=64, blank=True, default="")
    # Token stocké uniquement le temps du job (effacé à la fin)
    remote_token = models.CharField(max_length=4096, blank=True, default="")
    remote_username = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Username cPanel distant à transférer.",
    )
    remote_insecure_ssl = models.BooleanField(default=False)

    # Options (composants)
    options = models.JSONField(
        default=dict,
        blank=True,
        help_text='Ex: {"home": true, "databases": true, "email": true, "dns": true, "ssl": true, "ftp": true}',
    )

    progress = models.PositiveSmallIntegerField(default=0)
    current_step = models.CharField(max_length=255, blank=True, default="")
    log = models.TextField(blank=True, default="")
    result = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True, default="")

    created_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfer_jobs_created_users",
    )

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["username"]),
        ]

    def __str__(self) -> str:
        return f"transfer:{self.username}:{self.status}"

    def append_log(self, line: str) -> None:
        stamp = self.updated_at.isoformat(timespec="seconds") if self.updated_at else ""
        prefix = f"[{stamp}] " if stamp else ""
        self.log = (self.log + f"{prefix}{line}\n")[-200_000:]
