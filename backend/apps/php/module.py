from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="php",
        label="PHP multi-version",
        version="0.10.0",
        description="Versions PHP, sélecteur par domaine/chemin, php.ini, pools FPM.",
        dependencies=("core", "accounts", "files"),
        api_prefix="php",
        permissions=("php.view", "php.manage"),
        enabled_by_default=True,
    )
)
