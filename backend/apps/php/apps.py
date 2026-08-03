from __future__ import annotations

from django.apps import AppConfig


class PhpConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.php"
    label = "php"
    verbose_name = "PHP multi-version"
