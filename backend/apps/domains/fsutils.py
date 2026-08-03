"""Permissions filesystem pour homes et docroots domaines."""
from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

logger = logging.getLogger(__name__)


def chmod_path(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError as exc:
        logger.debug("chmod %s → %s: %s", path, oct(mode), exc)


def secure_directory(path: Path, mode: int = 0o755) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    chmod_path(path, mode)
    return path


def secure_file(path: Path, mode: int = 0o644) -> None:
    if path.exists():
        chmod_path(path, mode)


def apply_tree_permissions(root: Path, *, dir_mode: int = 0o755, file_mode: int = 0o644) -> None:
    if not root.exists():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        chmod_path(Path(dirpath), dir_mode)
        for name in filenames:
            chmod_path(Path(dirpath) / name, file_mode)


def try_chown_vzone(path: Path) -> None:
    """Attribue à l'utilisateur système vzone si possible (Linux)."""
    try:
        import grp
        import pwd

        uid = pwd.getpwnam("vzone").pw_uid
        gid = grp.getgrnam("vzone").gr_gid
    except (ImportError, KeyError):
        return
    try:
        for dirpath, _dirnames, filenames in os.walk(path):
            os.chown(dirpath, uid, gid)
            for name in filenames:
                os.chown(Path(dirpath) / name, uid, gid)
    except (PermissionError, OSError) as exc:
        logger.debug("chown vzone skip %s: %s", path, exc)
