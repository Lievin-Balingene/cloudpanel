from __future__ import annotations

from django.apps import AppConfig


class PanelApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.panel_api"
    label = "panel_api"
    verbose_name = "API jetons (style cPanel)"
