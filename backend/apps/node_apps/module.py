from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="node_apps",
        label="Applications Node.js",
        version="0.9.0",
        description="Apps Node.js : npm, démarrage, package.json, logs.",
        dependencies=("core", "accounts", "files"),
        api_prefix="node",
        permissions=("node_apps.view", "node_apps.manage"),
        enabled_by_default=True,
    )
)
