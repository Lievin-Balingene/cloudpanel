from __future__ import annotations

from django.apps import AppConfig


class CronConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cron"
    label = "cron"
    verbose_name = "Cron Jobs"
