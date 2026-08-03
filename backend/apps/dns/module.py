from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="dns",
        label="DNS",
        version="0.1.0",
        description="Zones DNS, enregistrements et DNSSEC.",
        dependencies=("core", "accounts"),
        api_prefix="dns",
        permissions=("dns.view", "dns.manage"),
        enabled_by_default=True,
    )
)
