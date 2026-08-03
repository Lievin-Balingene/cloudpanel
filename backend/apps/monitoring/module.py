from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="monitoring",
        label="Monitoring & Alertes",
        version="0.14.0",
        description="Seuils serveur, alertes, notifications e-mail.",
        dependencies=("core", "accounts", "dashboard"),
        api_prefix="monitoring",
        permissions=("monitoring.view", "monitoring.manage"),
        enabled_by_default=True,
    )
)
