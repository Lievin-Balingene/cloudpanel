from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="docker_mgmt",
        label="Docker",
        version="0.12.0",
        description="Panel Docker : conteneurs, images, build Dockerfile, Compose.",
        dependencies=("core", "accounts"),
        api_prefix="docker",
        permissions=("docker.view", "docker.manage"),
        enabled_by_default=True,
    )
)
