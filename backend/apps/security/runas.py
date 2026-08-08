"""Exécution de commandes sous l'UID client (anti RCE → vzone → root)."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Mapping

from django.conf import settings

from apps.core.exceptions import VZoneAPIException

RUNAS = Path("/usr/local/sbin/vzone-runas")
_SAFE_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RESERVED = frozenset(
    {
        "root",
        "vzone",
        "vmail",
        "nobody",
        "www",
        "www-data",
        "admin",
        "mysql",
        "postgres",
        "ftp",
        "mail",
    }
)


def runas_available() -> bool:
    return RUNAS.is_file() and os.access(RUNAS, os.X_OK)


def _validate_username(username: str) -> str:
    name = (username or "").strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_-]{2,31}", name):
        raise VZoneAPIException(
            detail="Username OS invalide pour runas.",
            code="invalid_runas_user",
            status_code=400,
        )
    if name in _RESERVED:
        raise VZoneAPIException(
            detail="Compte privilégié interdit pour runas.",
            code="forbidden_runas_user",
            status_code=403,
        )
    return name


def build_runas_cmd(
    username: str,
    cmd: list[str],
    *,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """Construit ``sudo -n vzone-runas user -- [env K=V … --] cmd…``."""
    user = _validate_username(username)
    if not cmd:
        raise VZoneAPIException(detail="Commande vide.", code="empty_cmd", status_code=400)
    if not runas_available():
        # Dev / mock : exécution directe (jamais en prod avec VZONE_LINUX_USER_PROVISION=live)
        mode = str(getattr(settings, "VZONE_LINUX_USER_PROVISION", "auto") or "auto").lower()
        if mode == "mock" or getattr(settings, "VZONE_ALLOW_UNJAILED_SUBPROCESS", False):
            return list(cmd)
        raise VZoneAPIException(
            detail="vzone-runas absent — sudo bash scripts/ensure-mkhome-sudoers.sh",
            code="runas_missing",
            status_code=500,
        )
    out: list[str] = ["sudo", "-n", str(RUNAS), user, "--"]
    if env:
        out.append("env")
        for key, val in env.items():
            if not _SAFE_ENV_KEY.fullmatch(str(key)):
                continue
            # Évite injection via newlines dans les valeurs env
            safe_val = str(val).replace("\n", " ").replace("\r", " ")
            out.append(f"{key}={safe_val}")
        out.append("--")
    out.extend(str(c) for c in cmd)
    return out


def run_as_user(
    username: str,
    cmd: list[str],
    *,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: int = 300,
    check: bool = True,
) -> subprocess.CompletedProcess:
    full = build_runas_cmd(username, cmd, env=env)
    try:
        return subprocess.run(
            full,
            check=check,
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd else None,
            timeout=timeout,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        stderr = getattr(exc, "stderr", None) or str(exc)
        raise VZoneAPIException(
            detail="Échec commande jailée.",
            code="runas_failed",
            status_code=502,
            extra={"stderr": stderr, "cmd": full},
        ) from exc
