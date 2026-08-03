from __future__ import annotations

from django.apps import AppConfig


class DnsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dns"
    label = "dns"
    verbose_name = "DNS"
