"""Modèles conteneurs Docker."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class DockerContainer(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Créé"
        RUNNING = "running", "En cours"
        STOPPED = "stopped", "Arrêté"
        ERROR = "error", "Erreur"
        REMOVED = "removed", "Supprimé"

    class RestartPolicy(models.TextChoices):
        NO = "no", "No"
        ALWAYS = "always", "Always"
        UNLESS_STOPPED = "unless-stopped", "Unless stopped"
        ON_FAILURE = "on-failure", "On failure"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="docker_containers",
    )
    name = models.CharField(max_length=64, db_index=True)
    label = models.CharField(max_length=120, blank=True, default="")
    image = models.CharField(max_length=255)
    tag = models.CharField(max_length=64, default="latest")
    container_id = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CREATED)
    ports = models.JSONField(
        default=dict,
        blank=True,
        help_text='Mapping ports host→container, ex: {"8080": "80"}.',
    )
    env_vars = models.JSONField(default=dict, blank=True)
    volumes = models.JSONField(
        default=list,
        blank=True,
        help_text='Volumes relatifs au home, ex: ["data:/app/data"].',
    )
    command = models.CharField(max_length=512, blank=True, default="")
    restart_policy = models.CharField(
        max_length=32,
        choices=RestartPolicy.choices,
        default=RestartPolicy.UNLESS_STOPPED,
    )
    memory_mb = models.PositiveIntegerField(default=512)
    cpus = models.DecimalField(max_digits=4, decimal_places=2, default=1)
    last_error = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
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

    @property
    def image_ref(self) -> str:
        return f"{self.image}:{self.tag}" if self.tag else self.image


class DockerContainerLog(models.Model):
    class Event(models.TextChoices):
        CREATE = "create", "Create"
        START = "start", "Start"
        STOP = "stop", "Stop"
        RESTART = "restart", "Restart"
        REMOVE = "remove", "Remove"
        LOGS = "logs", "Logs"

    container = models.ForeignKey(
        DockerContainer,
        on_delete=models.CASCADE,
        related_name="event_logs",
    )
    event_type = models.CharField(max_length=16, choices=Event.choices)
    success = models.BooleanField(default=True)
    message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.container_id}:{self.event_type}"
