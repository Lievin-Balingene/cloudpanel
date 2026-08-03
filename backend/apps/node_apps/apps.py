from __future__ import annotations

from django.apps import AppConfig


class NodeAppsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.node_apps"
    label = "node_apps"
    verbose_name = "Applications Node.js"
