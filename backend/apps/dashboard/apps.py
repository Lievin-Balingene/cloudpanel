from __future__ import annotations

from django.apps import AppConfig


class DashboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dashboard"
    label = "dashboard"
    verbose_name = "Tableau de bord"

    def ready(self) -> None:
        from apps.dashboard import tasks  # noqa: F401
