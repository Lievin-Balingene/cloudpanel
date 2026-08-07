"""Provision / vérification des comptes Linux jailés (cron, terminal)."""
from __future__ import annotations

import logging
import os
import pwd
import subprocess
from pathlib import Path

from django.conf import settings

from apps.accounts.models import User
from apps.accounts.services import RESERVED_USERNAMES, validate_system_username
from apps.core.exceptions import VZoneAPIException

logger = logging.getLogger(__name__)

CLIENTS_GROUP = "vzone-clients"


def linux_user_mode() -> str:
    """auto | live | mock — mock = pas de useradd (tests)."""
    return str(getattr(settings, "VZONE_LINUX_USER_PROVISION", "auto") or "auto").lower()


def jail_username_for(user: User) -> str:
    if user.role == User.Role.ADMINISTRATOR:
        # Admin panel process ≠ root OS ; pas de shell admin OS via terminal client.
        name = (user.system_username or "vzadmin").strip().lower() or "vzadmin"
        if name in RESERVED_USERNAMES or name == "root":
            name = "vzadmin"
        return name
    return validate_system_username(user.system_username or user.username)


def linux_user_exists(username: str) -> bool:
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False
    except ImportError:
        return False


def user_in_clients_group(username: str) -> bool:
    """True si username a vzone-clients en primaire ou complémentaire."""
    try:
        import grp

        g = grp.getgrnam(CLIENTS_GROUP)
    except (KeyError, ImportError):
        return False
    try:
        pw = pwd.getpwnam(username)
    except KeyError:
        return False
    if pw.pw_gid == g.gr_gid:
        return True
    if username in g.gr_mem:
        return True
    # Groupes complémentaires (getgrouplist)
    try:
        import os

        gids = os.getgrouplist(username, pw.pw_gid)
        return g.gr_gid in gids
    except (AttributeError, OSError):
        return False


def _ensure_clients_group() -> None:
    try:
        import grp

        grp.getgrnam(CLIENTS_GROUP)
        return
    except KeyError:
        pass
    except ImportError:
        return
    try:
        subprocess.run(
            ["groupadd", "--system", CLIENTS_GROUP],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("groupadd %s: %s", CLIENTS_GROUP, exc)


def provision_home_via_root(username: str) -> None:
    """Appelle /usr/local/sbin/vzone-mkhome via sudo (création /home sous root)."""
    helper = Path("/usr/local/sbin/vzone-mkhome")
    if not helper.is_file():
        raise VZoneAPIException(
            detail="Helper vzone-mkhome absent. Installez: sudo bash scripts/ensure-mkhome-sudoers.sh",
            code="mkhome_missing",
            status_code=500,
        )
    try:
        proc = subprocess.run(
            ["sudo", "-n", str(helper), username],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        raise VZoneAPIException(
            detail=f"sudo vzone-mkhome échoué: {exc}",
            code="mkhome_failed",
            status_code=500,
        ) from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise VZoneAPIException(
            detail=f"vzone-mkhome: {err or proc.returncode}",
            code="mkhome_failed",
            status_code=500,
        )


def ensure_linux_user(user: User, *, home: Path | None = None) -> str:
    """
    Garantit un UID Linux distinct du service vzone pour cron/terminal.
    Empêche l'exécution des jobs clients sous l'identité du panneau.
    """
    username = jail_username_for(user)
    if username in RESERVED_USERNAMES or username == "root":
        raise VZoneAPIException(
            detail=f"Compte OS réservé: {username}",
            code="reserved_os_user",
            status_code=400,
        )

    mode = linux_user_mode()
    if mode == "mock" or os.name == "nt":
        return username

    from apps.files.services import personal_home

    home_path = Path(home) if home else personal_home(user)
    helper = Path("/usr/local/sbin/vzone-mkhome")

    # Compte déjà là + dans vzone-clients → OK (sudoers terminal)
    if linux_user_exists(username) and user_in_clients_group(username):
        return username

    # Préférer le helper root (useradd + membership + ACL) — le panel n'est pas root
    if helper.is_file():
        try:
            provision_home_via_root(username)
            if linux_user_exists(username):
                if not user_in_clients_group(username):
                    logger.warning("%s toujours hors %s après mkhome", username, CLIENTS_GROUP)
                return username
        except VZoneAPIException as exc:
            logger.warning("mkhome via root: %s", exc)

    if linux_user_exists(username):
        return username

    if mode == "auto" and not Path("/usr/sbin/useradd").is_file() and not Path("/usr/bin/useradd").is_file():
        logger.warning("useradd indisponible — compte OS non créé pour %s", username)
        return username

    try:
        home_path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    _ensure_clients_group()

    cmd = [
        "sudo",
        "-n",
        "useradd",
        "-M",
        "-d",
        str(home_path),
        "-s",
        "/bin/bash",
        "-g",
        CLIENTS_GROUP,
        username,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        logger.error("useradd %s failed: %s", username, exc)
        return username

    if proc.returncode != 0 and not linux_user_exists(username):
        logger.warning("useradd %s: %s", username, (proc.stderr or proc.stdout or "").strip())
        return username

    logger.info("Compte Linux créé: %s home=%s", username, home_path)
    return username
