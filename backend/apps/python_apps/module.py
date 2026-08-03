from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="python_apps",
        label="Applications Python",
        version="0.8.0",
        description="Apps Python WSGI/ASGI : venv, démarrage, requirements, logs.",
        dependencies=("core", "accounts", "files"),
        api_prefix="python",
        permissions=("python_apps.view", "python_apps.manage"),
        enabled_by_default=True,
    )
)
