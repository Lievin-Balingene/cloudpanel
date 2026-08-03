"""Déclaration du module accounts."""
from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="accounts",
        label="Comptes",
        version="0.1.0",
        description="Utilisateurs, rôles (admin/revendeur/client), quotas et JWT.",
        dependencies=("core",),
        api_prefix="auth",
        permissions=(
            "accounts.view_user",
            "accounts.manage_user",
            "accounts.manage_quota",
        ),
        enabled_by_default=True,
    )
)
