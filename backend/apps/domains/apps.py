from __future__ import annotations

from django.apps import AppConfig


class DomainsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.domains"
    label = "domains"
    verbose_name = "Domaines"

    def ready(self) -> None:
        from apps.domains import tasks  # noqa: F401
