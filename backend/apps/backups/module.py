from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="backups",
        label="Backups",
        version="0.33.0",
        description="Sauvegardes Restic chiffrées via Rclone (local/S3/B2/R2/SFTP/Drive), async Celery, rétention.",
        dependencies=("core", "accounts"),
        api_prefix="backups",
        permissions=("backups.view", "backups.manage"),
        enabled_by_default=True,
    )
)
