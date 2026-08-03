from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="email",
        label="E-mail",
        version="0.17.0",
        description="Postfix/Dovecot/OpenDKIM — boîtes, aliases, SPF/DKIM/DMARC, maps live.",
        dependencies=("core", "accounts", "domains", "dns"),
        api_prefix="email",
        permissions=("email.view", "email.manage"),
        enabled_by_default=True,
    )
)
