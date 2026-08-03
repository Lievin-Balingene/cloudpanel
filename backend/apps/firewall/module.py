from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="firewall",
        label="Firewall & Fail2Ban",
        version="0.15.0",
        description="Règles firewall, jails Fail2Ban, ban/unban IP.",
        dependencies=("core", "accounts"),
        api_prefix="firewall",
        permissions=("firewall.view", "firewall.manage"),
        enabled_by_default=True,
    )
)
