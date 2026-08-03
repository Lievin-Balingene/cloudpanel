from __future__ import annotations

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"
    verbose_name = "V-zone Core"

    def ready(self) -> None:
        from apps.core.module_registry import registry

        registry.autodiscover()
