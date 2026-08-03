from __future__ import annotations

from django.apps import AppConfig


class DatabasesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.databases"
    label = "databases"
    verbose_name = "Bases de données"
