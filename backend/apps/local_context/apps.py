from __future__ import annotations

from django.apps import AppConfig


class LocalContextConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.local_context"
    label = "local_context"
    verbose_name = "Contexte local"
