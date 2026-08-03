from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="backups",
        label="Backups",
        version="0.13.0",
        description="Sauvegardes compte : création, restauration, planning, téléchargement.",
        dependencies=("core", "accounts"),
        api_prefix="backups",
        permissions=("backups.view", "backups.manage"),
        enabled_by_default=True,
    )
)
