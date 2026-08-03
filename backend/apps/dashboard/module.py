from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="dashboard",
        label="Dashboard",
        version="0.1.0",
        description="Métriques serveur, historique et vue d'ensemble WHM/client.",
        dependencies=("core", "accounts"),
        api_prefix="dashboard",
        permissions=("dashboard.view",),
        enabled_by_default=True,
    )
)
