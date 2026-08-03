from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="security",
        label="Sécurité avancée",
        version="0.16.0",
        description="2FA, lockout, allowlist IP panel, politique mots de passe.",
        dependencies=("core", "accounts"),
        api_prefix="security",
        permissions=("security.view", "security.manage"),
        enabled_by_default=True,
    )
)
