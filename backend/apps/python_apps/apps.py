from __future__ import annotations

from django.apps import AppConfig


class PythonAppsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.python_apps"
    label = "python_apps"
    verbose_name = "Applications Python"
