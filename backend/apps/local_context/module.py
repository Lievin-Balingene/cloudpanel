"""Déclaration du module contexte local."""
from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="local_context",
        label="Contexte local",
        version="0.41.0",
        description=(
            "Pays, fuseau, économie de données, panneau allégé, sauvegardes de nuit "
            "et reprise après coupure — exploitation du panneau, pas de facturation."
        ),
        dependencies=("core", "accounts", "packages"),
        api_prefix="local-context",
        permissions=("local_context.view", "local_context.manage"),
        enabled_by_default=True,
    )
)
