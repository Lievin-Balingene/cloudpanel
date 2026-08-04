from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="server_setup",
        label="Basic Server Setup",
        version="0.22.0",
        description="Hostname serveur et nameservers par défaut (WHM).",
        dependencies=("core", "accounts", "dns"),
        api_prefix="server-setup",
        permissions=("server_setup.view", "server_setup.manage"),
        enabled_by_default=True,
    )
)
