"""Disk used pour List Accounts — cache rapide (pas de du bloquant N comptes)."""
from __future__ import annotations

import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_TTL = 600  # 10 min
CACHE_PREFIX = "acct_disk_mb:"


def _home_for(user) -> Path | None:  # type: ignore[no-untyped-def]
    root = Path(getattr(settings, "VZONE_HOME_ROOT", "/home")).resolve()
    name = (getattr(user, "system_username", None) or user.username or "").strip().lower()
    if not name or name in {".", "..", "root", "home"} or "/" in name:
        return None
    home = (root / name).resolve()
    try:
        if home.parent != root or not home.is_dir():
            return None
    except OSError:
        return None
    return home


def _du_mb(home: Path) -> float | None:
    try:
        proc = subprocess.run(
            ["du", "-sm", "--", str(home)],
            capture_output=True,
            text=True,
            timeout=2.5,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return float(proc.stdout.split()[0])
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired, OSError):
        return None
    return None


def get_cached_disk_mb(user_id: int) -> float | None:
    val = cache.get(f"{CACHE_PREFIX}{user_id}")
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def set_cached_disk_mb(user_id: int, mb: float) -> None:
    cache.set(f"{CACHE_PREFIX}{user_id}", float(mb), timeout=CACHE_TTL)


def batch_disk_used_mb(users: Iterable, *, refresh_missing: bool = True) -> dict[int, float | None]:
    """
    Retourne disk used (Mo) pour une page d'utilisateurs.
    Utilise le cache ; recalcule en parallèle seulement les manquants (page courante).
    """
    users = list(users)
    out: dict[int, float | None] = {}
    missing = []
    for u in users:
        cached = get_cached_disk_mb(u.pk)
        if cached is not None:
            out[u.pk] = cached
        else:
            missing.append(u)
            out[u.pk] = None

    if not refresh_missing or not missing:
        return out

    def _one(u):  # type: ignore[no-untyped-def]
        home = _home_for(u)
        if not home:
            return u.pk, 0.0
        mb = _du_mb(home)
        return u.pk, mb

    # Limite le parallélisme pour ne pas saturer le disque
    workers = min(6, len(missing))
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_one, u) for u in missing]
            for fut in as_completed(futs, timeout=8):
                try:
                    uid, mb = fut.result()
                    if mb is not None:
                        set_cached_disk_mb(uid, mb)
                        out[uid] = mb
                except Exception:  # noqa: BLE001
                    logger.debug("disk batch item failed", exc_info=True)
    except Exception:  # noqa: BLE001
        logger.debug("disk batch failed", exc_info=True)

    return out
