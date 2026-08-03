"""Modèles applications Node.js hébergées."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class NodeApp(models.Model):
    class Framework(models.TextChoices):
        GENERIC = "generic", "Générique"
        EXPRESS = "express", "Express"
        NEST = "nest", "NestJS"
        NEXT = "next", "Next.js"

    class Status(models.TextChoices):
        STOPPED = "stopped", "Arrêtée"
        RUNNING = "running", "En cours"
        ERROR = "error", "Erreur"
        PROVISIONING = "provisioning", "Provisionnement"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="node_apps",
    )
    name = models.CharField(max_length=64, db_index=True)
    label = models.CharField(max_length=120, blank=True, default="")
    node_version = models.CharField(max_length=16, default="20")
    framework = models.CharField(
        max_length=16,
        choices=Framework.choices,
        default=Framework.GENERIC,
    )
    relative_root = models.CharField(
        max_length=255,
        default="",
        help_text="Chemin relatif au home (ex: nodeapps/myapp).",
    )
    start_script = models.CharField(
        max_length=64,
        default="start",
        help_text="Script npm (package.json scripts).",
    )
    entrypoint = models.CharField(
        max_length=255,
        default="server.js",
        help_text="Fichier d'entrée si pas de script npm.",
    )
    port = models.PositiveIntegerField(default=0)
    env_vars = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.STOPPED)
    pid = models.PositiveIntegerField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    domain_name = models.CharField(max_length=255, blank=True, default="")
    notes = models.CharField(max_length=255, blank=True, default="")
    last_started_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        unique_together = ("owner", "name")
        indexes = [models.Index(fields=["owner", "status"])]

    def __str__(self) -> str:
        return f"{self.owner.username}/{self.name}"
