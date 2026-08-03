from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="databases",
        label="Bases de données",
        version="0.7.0",
        description="MySQL/MariaDB et PostgreSQL : bases, utilisateurs, privilèges.",
        dependencies=("core", "accounts"),
        api_prefix="databases",
        permissions=("databases.view", "databases.manage"),
        enabled_by_default=True,
    )
)
