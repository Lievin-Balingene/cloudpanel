from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="email",
        label="E-mail",
        version="0.6.0",
        description="Boîtes mail, aliases, forwarders, répondeurs, SPF/DKIM/DMARC.",
        dependencies=("core", "accounts", "domains", "dns"),
        api_prefix="email",
        permissions=("email.view", "email.manage"),
        enabled_by_default=True,
    )
)
