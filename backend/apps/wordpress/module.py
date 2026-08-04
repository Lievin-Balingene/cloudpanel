from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="wordpress",
        label="WordPress",
        version="0.20.0",
        description="Installation et gestion de sites WordPress (wp-cli, MySQL, PHP-FPM).",
        dependencies=("core", "accounts", "domains", "databases", "php", "files"),
        api_prefix="wordpress",
        permissions=("wordpress.view", "wordpress.manage"),
        enabled_by_default=True,
    )
)
