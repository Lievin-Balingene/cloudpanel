"""Déclaration du module packages."""
from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="packages",
        label="Packages",
        version="0.1.0",
        description="Plans d'hébergement client/revendeur et synchronisation des quotas.",
        dependencies=("core", "accounts"),
        api_prefix="packages",
        permissions=(
            "packages.view",
            "packages.manage",
            "packages.assign",
        ),
        enabled_by_default=True,
    )
)
