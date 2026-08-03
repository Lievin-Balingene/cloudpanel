from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="domains",
        label="Domaines",
        version="0.3.0",
        description="Domaines principaux, alias, sous-domaines, parked et redirections.",
        dependencies=("core", "accounts", "dns", "packages"),
        api_prefix="domains",
        permissions=("domains.view", "domains.manage"),
        enabled_by_default=True,
    )
)
