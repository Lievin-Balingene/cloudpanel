"""Modèles applications Python hébergées."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class PythonApp(models.Model):
    class Mode(models.TextChoices):
        WSGI = "wsgi", "WSGI"
        ASGI = "asgi", "ASGI"

    class Framework(models.TextChoices):
        GENERIC = "generic", "Générique"
        DJANGO = "django", "Django"
        FLASK = "flask", "Flask"
        FASTAPI = "fastapi", "FastAPI"

    class Status(models.TextChoices):
        STOPPED = "stopped", "Arrêtée"
        RUNNING = "running", "En cours"
        ERROR = "error", "Erreur"
        PROVISIONING = "provisioning", "Provisionnement"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="python_apps",
    )
    name = models.CharField(max_length=64, db_index=True)
    label = models.CharField(max_length=120, blank=True, default="")
    python_version = models.CharField(max_length=16, default="3.12")
    mode = models.CharField(max_length=8, choices=Mode.choices, default=Mode.WSGI)
    framework = models.CharField(
        max_length=16,
        choices=Framework.choices,
        default=Framework.GENERIC,
    )
    relative_root = models.CharField(
        max_length=255,
        default="",
        help_text="Application root cPanel : chemin du projet relatif au home (ex: mydjango). "
        "passenger_wsgi.py et manage.py doivent être dans ce même dossier.",
    )
    entrypoint = models.CharField(
        max_length=255,
        default="passenger_wsgi.py",
        help_text="Module/fichier d'entrée (passenger_wsgi.py ou app:app).",
    )
    port = models.PositiveIntegerField(default=0)
    env_vars = models.JSONField(default=dict, blank=True)
    requirements_file = models.CharField(max_length=64, default="requirements.txt")
    venv_path = models.CharField(max_length=512, blank=True, default="")
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
