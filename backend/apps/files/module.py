from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="files",
        label="Fichiers",
        version="0.4.0",
        description="File Manager sécurisé : upload, édition, compression, permissions.",
        dependencies=("core", "accounts"),
        api_prefix="files",
        permissions=("files.view", "files.manage"),
        enabled_by_default=True,
    )
)
