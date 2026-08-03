from __future__ import annotations

from django.apps import AppConfig


class DockerMgmtConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.docker_mgmt"
    label = "docker_mgmt"
    verbose_name = "Docker"
