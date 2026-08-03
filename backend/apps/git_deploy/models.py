"""Modèles Git Version Control."""
from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models


class GitRepository(models.Model):
    class Status(models.TextChoices):
        IDLE = "idle", "Inactif"
        CLONING = "cloning", "Clone"
        DEPLOYING = "deploying", "Déploiement"
        READY = "ready", "Prêt"
        ERROR = "error", "Erreur"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="git_repositories",
    )
    name = models.CharField(max_length=64, db_index=True)
    label = models.CharField(max_length=120, blank=True, default="")
    remote_url = models.CharField(max_length=512)
    branch = models.CharField(max_length=128, default="main")
    relative_path = models.CharField(
        max_length=255,
        help_text="Chemin relatif au home (ex: repositories/app).",
    )
    deploy_script = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Script post-pull relatif au dépôt (ex: deploy.sh).",
    )
    auto_deploy = models.BooleanField(default=True)
    webhook_token = models.CharField(max_length=64, unique=True, db_index=True)
    deploy_key_public = models.TextField(blank=True, default="")
    deploy_key_private = models.TextField(blank=True, default="")
    last_commit = models.CharField(max_length=64, blank=True, default="")
    last_commit_message = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IDLE)
    last_error = models.TextField(blank=True, default="")
    last_deploy_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        unique_together = ("owner", "name")
        indexes = [models.Index(fields=["owner", "status"])]

    def __str__(self) -> str:
        return f"{self.owner.username}/{self.name}"

    @staticmethod
    def generate_webhook_token() -> str:
        return secrets.token_urlsafe(24)


class GitDeployLog(models.Model):
    class Event(models.TextChoices):
        CLONE = "clone", "Clone"
        PULL = "pull", "Pull"
        DEPLOY = "deploy", "Deploy"
        WEBHOOK = "webhook", "Webhook"
        KEYGEN = "keygen", "Clé deploy"

    repository = models.ForeignKey(
        GitRepository,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    event_type = models.CharField(max_length=16, choices=Event.choices)
    success = models.BooleanField(default=True)
    message = models.TextField(blank=True, default="")
    commit_hash = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["repository", "created_at"])]

    def __str__(self) -> str:
        return f"{self.repository_id}:{self.event_type}"
