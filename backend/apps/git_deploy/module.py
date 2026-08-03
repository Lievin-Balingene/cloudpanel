from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="git_deploy",
        label="Git Deploy",
        version="0.11.0",
        description="Clone, pull, webhooks et déploiements Git dans le home utilisateur.",
        dependencies=("core", "accounts", "files"),
        api_prefix="git",
        permissions=("git_deploy.view", "git_deploy.manage"),
        enabled_by_default=True,
    )
)
