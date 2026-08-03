from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="ftp",
        label="FTP",
        version="0.5.0",
        description="Comptes FTP, suspension, quotas et journaux d'accès.",
        dependencies=("core", "accounts", "files"),
        api_prefix="ftp",
        permissions=("ftp.view", "ftp.manage"),
        enabled_by_default=True,
    )
)
