"""Déclaration du module core."""
from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="core",
        label="Noyau",
        version="0.1.0",
        description="Services transverses : santé, registre, audit, pagination.",
        api_prefix="core",
        permissions=("core.view_health", "core.view_modules"),
        enabled_by_default=True,
    )
)
