from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="kubernetes",
        label="Kubernetes",
        version="0.21.0",
        description="Gestion Kubernetes : namespaces, pods, déploiements, apply/delete YAML.",
        dependencies=("core", "accounts"),
        api_prefix="kubernetes",
        permissions=("kubernetes.view", "kubernetes.manage"),
        enabled_by_default=True,
    )
)
