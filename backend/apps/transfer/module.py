from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="transfer",
        label="Transfer Tool",
        version="0.23.0",
        description=(
            "Transfert de comptes cPanel/WHM (archives pkgacct/cpmove et serveur distant) "
            "vers V-zone sans perte de données."
        ),
        dependencies=("core", "accounts", "domains", "email", "databases", "dns", "ftp"),
        api_prefix="transfer",
        permissions=("transfer.view", "transfer.manage"),
        enabled_by_default=True,
    )
)
