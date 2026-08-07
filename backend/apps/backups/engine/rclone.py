"""Wrapper Rclone — abstraction stockage."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.backups.engine import run_cmd
from apps.backups.engine.providers import build_rclone_section, provider_path

logger = logging.getLogger(__name__)

SAFE_REMOTE_RE = re.compile(r"^[a-zA-Z0-9_-]{2,64}$")


def rclone_bin() -> str:
    return str(getattr(settings, "VZONE_RCLONE_BIN", "rclone") or "rclone")


def rclone_config_dir() -> Path:
    root = Path(
        getattr(settings, "VZONE_BACKUP_DIR", None)
        or (Path(settings.VZONE_DATA_ROOT) / "backups")
    )
    path = root / "rclone"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path_for(destination_id: int) -> Path:
    return rclone_config_dir() / f"dest-{destination_id}.conf"


def write_rclone_config(
    *,
    destination_id: int,
    remote_name: str,
    provider: str,
    config: dict[str, Any],
    credentials: dict[str, Any],
) -> Path:
    if not SAFE_REMOTE_RE.match(remote_name):
        raise ValueError(f"Nom remote rclone invalide: {remote_name}")
    section = build_rclone_section(provider, remote_name, config, credentials)
    path = config_path_for(destination_id)
    path.write_text(section + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def repository_uri(
    *,
    provider: str,
    remote_name: str,
    config: dict[str, Any],
    local_fallback: Path,
) -> str:
    """Construit l'URI dépôt Restic (local path ou rclone:remote:path)."""
    if provider == "local":
        path = Path(config.get("path") or local_fallback)
        path.mkdir(parents=True, exist_ok=True)
        return str(path)
    path = provider_path(provider, config)
    return f"rclone:{remote_name}:{path}"


def rclone_env(config_file: Path) -> dict[str, str]:
    return {
        "RCLONE_CONFIG": str(config_file),
    }


def test_remote(config_file: Path, remote_name: str, path: str = "") -> tuple[bool, str]:
    target = f"{remote_name}:{path}" if path else f"{remote_name}:"
    result = run_cmd(
        [rclone_bin(), "lsd", target, "--config", str(config_file)],
        env=rclone_env(config_file),
        timeout=60,
    )
    if result.ok:
        return True, "ok"
    return False, result.output[:2000]
