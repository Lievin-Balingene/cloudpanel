from __future__ import annotations

from django.apps import AppConfig


class PackagesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.packages"
    label = "packages"
    verbose_name = "Packages d'hébergement"
