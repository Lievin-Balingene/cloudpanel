from __future__ import annotations

from django.apps import AppConfig


class ServerSetupConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.server_setup"
    label = "server_setup"
    verbose_name = "Configuration serveur WHM"
