from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="cron",
        label="Cron Jobs",
        version="0.30.0",
        description="Tâches planifiées style cPanel (crontab /etc/cron.d).",
        dependencies=("core", "accounts", "files"),
        api_prefix="cron",
        permissions=("cron.view", "cron.manage"),
        enabled_by_default=True,
    )
)
