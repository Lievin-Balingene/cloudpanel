"""Registre de modules indépendants V-zone Panel.

Chaque fonctionnalité (domaines, DNS, email, …) s'enregistre ici
pour activer routes API, permissions et hooks d'installation.
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Callable

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ModuleMeta:
    """Métadonnées d'un module V-zone."""

    name: str
    label: str
    version: str
    description: str
    dependencies: tuple[str, ...] = ()
    api_prefix: str = ""
    permissions: tuple[str, ...] = ()
    install_hooks: tuple[str, ...] = ()
    enabled_by_default: bool = True
    extra: dict = field(default_factory=dict)


Hook = Callable[[], None]


class ModuleRegistry:
    """Registre central des modules installés / activés."""

    def __init__(self) -> None:
        self._modules: dict[str, ModuleMeta] = {}
        self._hooks: dict[str, list[Hook]] = {}
        self._discovered = False

    def register(self, meta: ModuleMeta) -> None:
        if meta.name in self._modules:
            raise ValueError(f"Module déjà enregistré: {meta.name}")
        for dep in meta.dependencies:
            if dep not in self._modules and dep != meta.name:
                logger.debug(
                    "Module %s dépend de %s (pas encore chargé)",
                    meta.name,
                    dep,
                )
        self._modules[meta.name] = meta
        logger.info("Module enregistré: %s v%s", meta.name, meta.version)

    def add_hook(self, event: str, callback: Hook) -> None:
        self._hooks.setdefault(event, []).append(callback)

    def run_hooks(self, event: str) -> None:
        for callback in self._hooks.get(event, []):
            callback()

    def get(self, name: str) -> ModuleMeta | None:
        return self._modules.get(name)

    def all(self) -> list[ModuleMeta]:
        return list(self._modules.values())

    def enabled(self) -> list[ModuleMeta]:
        enabled_names = set(getattr(settings, "VZONE_ENABLED_MODULES", []))
        return [m for m in self._modules.values() if m.name in enabled_names]

    def is_enabled(self, name: str) -> bool:
        enabled_names = set(getattr(settings, "VZONE_ENABLED_MODULES", []))
        return name in enabled_names and name in self._modules

    def autodiscover(self) -> None:
        if self._discovered:
            return
        self._discovered = True
        # Modules de base toujours découverts
        module_paths = [
            "apps.core.module",
            "apps.accounts.module",
            "apps.packages.module",
            "apps.dns.module",
            "apps.dashboard.module",
            "apps.domains.module",
            "apps.files.module",
            "apps.ftp.module",
            "apps.email.module",
            "apps.databases.module",
            "apps.python_apps.module",
            "apps.node_apps.module",
            "apps.php.module",
            "apps.git_deploy.module",
            "apps.docker_mgmt.module",
            "apps.backups.module",
            "apps.monitoring.module",
            "apps.firewall.module",
            "apps.security.module",
            "apps.wordpress.module",
            "apps.kubernetes.module",
            "apps.server_setup.module",
            "apps.transfer.module",
        ]
        for path in module_paths:
            try:
                importlib.import_module(path)
            except ModuleNotFoundError:
                logger.warning("Impossible de charger le module: %s", path)


registry = ModuleRegistry()
