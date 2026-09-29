"""SMTP Restrictions (WHM) — bloque les sorties TCP/25 hors MTA / root / mailman."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from django.conf import settings

from apps.core.exceptions import VZoneAPIException

logger = logging.getLogger(__name__)

HELPER = Path("/usr/local/sbin/vzone-smtp-restrictions")
STATE_FILE = Path("/var/lib/vzone/smtp-restrictions/enabled")


def provision_mode() -> str:
    mode = getattr(settings, "VZONE_SMTP_RESTRICT_MODE", "auto").lower()
    if mode not in {"auto", "live", "mock"}:
        mode = "auto"
    if mode == "auto":
        if HELPER.is_file() or shutil.which("iptables"):
            return "live"
        return "mock"
    return mode


def _run_helper(action: str) -> dict:
    """Exécute vzone-smtp-restrictions via sudo (live) ou mock local."""
    if action not in {"status", "enable", "disable", "check"}:
        raise VZoneAPIException(detail="Action SMTP invalide.", code="invalid_action", status_code=400)

    if provision_mode() == "mock":
        return _mock_action(action)

    cmd = ["sudo", "-n", str(HELPER), f"--{action}"]
    if not HELPER.is_file():
        # Fallback: script depuis le dépôt source
        src = Path(getattr(settings, "VZONE_SRC_ROOT", "/opt/vzone-src")) / "scripts" / "vzone-smtp-restrictions.sh"
        if src.is_file():
            cmd = ["sudo", "-n", "bash", str(src), f"--{action}"]
        else:
            raise VZoneAPIException(
                detail=(
                    "Helper SMTP Restrictions absent. "
                    "Exécutez: sudo bash /opt/vzone-src/scripts/ensure-mkhome-sudoers.sh"
                ),
                code="smtp_restrict_helper_missing",
                status_code=503,
            )
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=45)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise VZoneAPIException(
            detail=f"Échec SMTP Restrictions: {exc}",
            code="smtp_restrict_failed",
            status_code=502,
        ) from exc

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        if "password is required" in err.lower() or "a password is required" in err.lower():
            err = (
                f"{err} — sudoers manquant. "
                "sudo bash /opt/vzone-src/scripts/ensure-mkhome-sudoers.sh"
            )
        raise VZoneAPIException(
            detail=f"SMTP Restrictions: {err[:400]}",
            code="smtp_restrict_failed",
            status_code=502,
            extra={"stderr": err[:2000]},
        )

    if action == "check":
        return {"ok": True}

    out = (proc.stdout or "").strip()
    if out.startswith("{"):
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            pass
    return {"enabled": action == "enable", "detail": out or action}


def _mock_action(action: str) -> dict:
    root = Path(getattr(settings, "VZONE_DATA_ROOT", "/var/lib/vzone")) / "smtp-restrictions"
    root.mkdir(parents=True, exist_ok=True)
    state = root / "enabled"
    if action == "enable":
        state.write_text("1", encoding="utf-8")
        return {
            "enabled": True,
            "mock": True,
            "detail": "SMTP restrictions actives (mock).",
            "allowed_users": ["root", "postfix", "mailman"],
            "ports": [25],
        }
    if action == "disable":
        state.write_text("0", encoding="utf-8")
        return {
            "enabled": False,
            "mock": True,
            "detail": "SMTP restrictions désactivées (mock).",
            "allowed_users": ["root", "postfix", "mailman"],
            "ports": [25],
        }
    if action == "check":
        return {"ok": True}
    enabled = state.read_text(encoding="utf-8").strip() == "1" if state.exists() else False
    return {
        "enabled": enabled,
        "mock": True,
        "state_file": enabled,
        "iptables_live": False,
        "allowed_users": ["root", "postfix", "mailman"],
        "ports": [25],
        "helper": "mock",
    }


def get_status() -> dict:
    data = _run_helper("status")
    enabled = bool(data.get("enabled"))
    return {
        "enabled": enabled,
        "disabled": not enabled,
        "message": (
            "The SMTP restriction is enabled."
            if enabled
            else "The SMTP restriction is disabled."
        ),
        "description": (
            "This feature prevents users from bypassing the mail server to send mail, "
            "a common practice used by spammers. It will allow only the MTA, mailman, "
            "and root to connect to remote SMTP servers."
        ),
        "ports": data.get("ports") or [25],
        "allowed_users": data.get("allowed_users") or [],
        "iptables_live": bool(data.get("iptables_live")),
        "mock": bool(data.get("mock")),
        "provision_mode": provision_mode(),
        "tweak_key": "smtp_restrictions",
    }


def set_enabled(enabled: bool) -> dict:
    data = _run_helper("enable" if enabled else "disable")
    # Sync Tweak Settings
    try:
        from apps.server_setup.models import ServerSetup
        from apps.server_setup.tweak_settings import merge_tweaks

        setup = ServerSetup.get_solo()
        merged = merge_tweaks(setup.tweak_settings)
        merged["smtp_restrictions"] = bool(enabled)
        setup.tweak_settings = merged
        setup.save(update_fields=["tweak_settings", "updated_at"])
    except Exception:  # noqa: BLE001
        logger.exception("sync tweak smtp_restrictions failed")
    status = get_status()
    status["detail"] = data.get("detail") or status["message"]
    return status


def apply_from_tweak(value: bool) -> None:
    """Appelé après sauvegarde Tweak Settings — best-effort."""
    try:
        current = get_status()
        if bool(current.get("enabled")) == bool(value):
            return
        set_enabled(bool(value))
    except Exception:  # noqa: BLE001
        logger.warning("apply smtp_restrictions from tweak failed", exc_info=True)
