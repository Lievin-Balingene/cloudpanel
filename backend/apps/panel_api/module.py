from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="panel_api",
        label="API jetons",
        version="1.0.0",
        description="Jetons d'API, WHM JSON API et UAPI (style cPanel) branchés sur les services du panneau.",
        dependencies=("core", "accounts"),
        api_prefix="api-tokens",
        permissions=("panel_api.manage",),
        enabled_by_default=True,
    )
)
