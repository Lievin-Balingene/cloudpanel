"""Mise à jour du panel depuis WHM (git sync + update.sh via agent root)."""
from __future__ import annotations

import json
import logging
import secrets
import shutil
import subprocess
import time
from pathlib import Path

from django.conf import settings

from apps.core.exceptions import VZoneAPIException
from vzone import get_version

logger = logging.getLogger(__name__)

AGENT_BIN = Path("/usr/local/sbin/vzone-update-agent")
PATH_UNIT = "vzone-update-job.path"
SERVICE_UNIT = "vzone-update-job.service"


def update_jobs_dir(*, create: bool = True) -> Path:
    root = Path(getattr(settings, "VZONE_DATA_ROOT", "/var/lib/vzone")) / "update" / "jobs"
    if create:
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("update jobs dir mkdir failed: %s", exc)
    return root


def _vzone_root() -> Path:
    return Path(getattr(settings, "VZONE_ROOT", "/opt/vzone"))


def resolve_src_dir() -> Path:
    """Trouve le dépôt source (git) — plusieurs emplacements courants."""
    candidates: list[Path] = []
    configured = (getattr(settings, "VZONE_SRC_DIR", "") or "").strip()
    if configured:
        candidates.append(Path(configured))
    candidates.extend(
        [
            Path("/opt/vzone-src"),
            _vzone_root().parent / "vzone-src",
            Path("/usr/local/src/vzone"),
            Path("/root/vzone"),
            Path("/root/vhost"),
        ]
    )
    # Si le runtime /opt/vzone contient encore .git (install atypique)
    runtime = _vzone_root()
    if (runtime / ".git").is_dir() and (runtime / "scripts" / "update.sh").is_file():
        candidates.insert(0, runtime)

    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        try:
            if path.is_dir() and (path / "scripts" / "update.sh").is_file():
                return path
            if path.is_dir() and (path / "VERSION").is_file():
                return path
        except OSError:
            continue
    return Path(configured or "/opt/vzone-src")


def default_src_dir() -> Path:
    return resolve_src_dir()


def agent_installed() -> bool:
    try:
        return AGENT_BIN.is_file() and os_access_ok(AGENT_BIN)
    except OSError:
        return False


def os_access_ok(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def path_unit_enabled() -> bool | None:
    systemctl = shutil.which("systemctl") or "/bin/systemctl"
    try:
        proc = subprocess.run(
            [systemctl, "is-enabled", PATH_UNIT],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    out = (proc.stdout or "").strip()
    if out == "enabled":
        return True
    if out in {"disabled", "masked"}:
        return False
    return None


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _tail_log(path: Path, *, max_chars: int = 24000) -> str:
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _clear_stale_lock(path: Path, *, max_age: int = 3600) -> bool:
    """Supprime un verrou périmé. Retourne True si le chemin n'existe plus."""
    if not path.exists():
        return True
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return False
    if age < max_age:
        return False
    try:
        if path.is_dir():
            path.rmdir()
        else:
            path.unlink(missing_ok=True)
    except OSError:
        return False
    return not path.exists()


def _job_busy() -> bool:
    jobs = update_jobs_dir(create=False)
    if not jobs.is_dir():
        return False
    for stale in list(jobs.glob("*.lock")) + list(jobs.glob("*.request")):
        _clear_stale_lock(stale, max_age=3600)

    if any(jobs.glob("*.request")) or any(jobs.glob("*.lock")):
        return True
    lock = jobs.parent / ".lock"
    if lock.is_file():
        if _clear_stale_lock(lock, max_age=3600):
            return False
        return True
    return False


def _git_src_info(src: Path) -> dict:
    info: dict = {
        "git_ok": False,
        "git_branch": "",
        "git_head": "",
        "git_remote": "",
        "git_error": "",
    }
    if not src.is_dir():
        info["git_error"] = "src absent"
        return info
    git = ["git", "-C", str(src)]
    try:
        head = subprocess.run(
            [*git, "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        branch = subprocess.run(
            [*git, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        remote = subprocess.run(
            [*git, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if head.returncode == 0:
            info["git_ok"] = True
            info["git_head"] = (head.stdout or "").strip()
            info["git_branch"] = (branch.stdout or "").strip() if branch.returncode == 0 else ""
            info["git_remote"] = (remote.stdout or "").strip() if remote.returncode == 0 else ""
        else:
            info["git_error"] = (head.stderr or head.stdout or "git error").strip()[:200]
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        info["git_error"] = str(exc)[:200]
    return info


def _read_version_file(*roots: Path) -> str:
    for root in roots:
        vf = root / "VERSION"
        try:
            if vf.is_file():
                return vf.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return ""


def _kick_update_service() -> tuple[bool, str]:
    """Démarre l'agent root (sudoers NOPASSWD ou path unit)."""
    systemctl = shutil.which("systemctl") or "/bin/systemctl"
    attempts: list[list[str]] = [
        ["sudo", "-n", systemctl, "start", SERVICE_UNIT],
        ["sudo", "-n", systemctl, "start", PATH_UNIT],
        [systemctl, "start", SERVICE_UNIT],
    ]
    last_err = ""
    for cmd in attempts:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
            last_err = str(exc)
            continue
        if proc.returncode == 0:
            return True, ""
        last_err = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()[:300]
    return False, last_err


def list_recent_jobs(*, limit: int = 8) -> list[dict]:
    jobs = update_jobs_dir(create=False)
    if not jobs.is_dir():
        return []
    items: list[dict] = []
    try:
        paths = sorted(jobs.glob("*.result"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []
    for path in paths[:limit]:
        data = _read_json(path) or {}
        items.append(
            {
                "job_id": path.stem,
                "ok": bool(data.get("ok")),
                "error": data.get("error") or "",
                "version_before": data.get("version_before") or "",
                "version_after": data.get("version_after") or "",
                "finished_at": data.get("finished_at") or "",
            }
        )
    try:
        status_paths = sorted(
            jobs.glob("*.status"), key=lambda p: p.stat().st_mtime, reverse=True
        )
    except OSError:
        status_paths = []
    for status_path in status_paths:
        if (jobs / f"{status_path.stem}.result").is_file():
            continue
        data = _read_json(status_path) or {}
        if data.get("state") == "running":
            items.insert(
                0,
                {
                    "job_id": status_path.stem,
                    "ok": None,
                    "pending": True,
                    "step": data.get("step") or "running",
                    "version_before": data.get("version_before") or "",
                    "started_at": data.get("started_at") or "",
                },
            )
    return items[:limit]


def panel_update_overview() -> dict:
    """Jamais lever : l'UI WHM doit toujours afficher un diagnostic."""
    try:
        src = resolve_src_dir()
        src_exists = False
        try:
            src_exists = src.is_dir()
        except OSError:
            src_exists = False

        runtime_version = ""
        try:
            runtime_version = get_version() or ""
        except Exception:  # noqa: BLE001
            runtime_version = ""
        if not runtime_version:
            runtime_version = _read_version_file(_vzone_root()) or "—"

        src_version = _read_version_file(src) if src_exists else ""
        git_info = _git_src_info(src) if src_exists else {
            "git_ok": False,
            "git_branch": "",
            "git_head": "",
            "git_remote": "",
            "git_error": "src absent",
        }
        agent_ok = agent_installed()
        path_enabled = path_unit_enabled() if agent_ok else None

        bootstrap_script = ""
        for candidate in (
            src / "scripts" / "install-update-agent.sh",
            _vzone_root() / "scripts" / "install-update-agent.sh",
        ):
            if candidate.is_file():
                bootstrap_script = str(candidate)
                break

        return {
            "version": runtime_version,
            "src_dir": str(src),
            "src_exists": src_exists,
            "src_version": src_version,
            "agent_installed": agent_ok,
            "path_unit_enabled": path_enabled,
            "busy": _job_busy(),
            "recent_jobs": list_recent_jobs(),
            "bootstrap_available": bool(bootstrap_script),
            "bootstrap_script": bootstrap_script,
            "vzone_root": str(_vzone_root()),
            "jobs_dir": str(update_jobs_dir(create=False)),
            "jobs_dir_writable": _jobs_writable(),
            **git_info,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("panel_update_overview failed")
        return {
            "version": "—",
            "src_dir": "/opt/vzone-src",
            "src_exists": False,
            "src_version": "",
            "agent_installed": False,
            "path_unit_enabled": None,
            "busy": False,
            "recent_jobs": [],
            "bootstrap_available": False,
            "bootstrap_script": "",
            "vzone_root": str(_vzone_root()),
            "jobs_dir": "",
            "jobs_dir_writable": False,
            "git_ok": False,
            "git_branch": "",
            "git_head": "",
            "git_remote": "",
            "git_error": str(exc)[:200],
            "overview_error": str(exc)[:300],
        }


def _jobs_writable() -> bool:
    jobs = update_jobs_dir(create=True)
    try:
        if not jobs.is_dir():
            return False
        probe = jobs / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def get_job_status(job_id: str) -> dict:
    job_id = (job_id or "").strip()
    if not job_id or "/" in job_id or ".." in job_id:
        raise VZoneAPIException(detail="job_id invalide.", code="invalid_job", status_code=400)

    jobs = update_jobs_dir(create=False)
    request = jobs / f"{job_id}.request"
    status = _read_json(jobs / f"{job_id}.status") or {}
    result = _read_json(jobs / f"{job_id}.result")
    log = _tail_log(jobs / f"{job_id}.log")

    if result is not None:
        return {
            "job_id": job_id,
            "state": "done" if result.get("ok") else "error",
            "pending": False,
            "ok": bool(result.get("ok")),
            "error": result.get("error") or "",
            "version_before": result.get("version_before") or "",
            "version_after": result.get("version_after") or "",
            "finished_at": result.get("finished_at") or "",
            "step": status.get("step") or ("finished" if result.get("ok") else "failed"),
            "log": log,
        }

    if request.is_file() or (jobs / f"{job_id}.lock").is_dir() or status.get("state") == "running":
        return {
            "job_id": job_id,
            "state": "running",
            "pending": True,
            "ok": None,
            "error": "",
            "version_before": status.get("version_before") or "",
            "version_after": "",
            "step": status.get("step") or "queued",
            "started_at": status.get("started_at") or "",
            "log": log,
        }

    raise VZoneAPIException(
        detail="Job de mise à jour introuvable.",
        code="job_not_found",
        status_code=404,
    )


def _find_install_script() -> Path | None:
    for candidate in (
        resolve_src_dir() / "scripts" / "install-update-agent.sh",
        _vzone_root() / "scripts" / "install-update-agent.sh",
    ):
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def bootstrap_update_agent() -> dict:
    """Installe l'agent root via sudo -n (sans SSH) si sudoers le permet."""
    if agent_installed():
        return {
            "ok": True,
            "already_installed": True,
            "agent_installed": True,
            "message": "Agent déjà installé.",
        }

    script = _find_install_script()
    if script is None:
        raise VZoneAPIException(
            detail=(
                "Script install-update-agent.sh introuvable. "
                "Vérifiez /opt/vzone-src ou /opt/vzone/scripts."
            ),
            code="bootstrap_script_missing",
            status_code=400,
        )

    bash = shutil.which("bash") or "/bin/bash"
    # Prefer absolute paths that match deploy/sudoers/vzone-panel
    for candidate in ("/bin/bash", "/usr/bin/bash", bash):
        if Path(candidate).is_file():
            bash = candidate
            break
    cmd = ["sudo", "-n", bash, str(script)]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        raise VZoneAPIException(
            detail=f"Impossible de lancer le bootstrap agent: {exc}",
            code="bootstrap_failed",
            status_code=500,
        ) from exc

    log = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()[-4000:]
    if proc.returncode != 0:
        raise VZoneAPIException(
            detail=(
                "Bootstrap agent refusé (sudoers manquant ou erreur). "
                "Une fois via SSH : sudo bash /opt/vzone-src/scripts/install-update-agent.sh"
                + (f"\n{log}" if log else "")
            ),
            code="bootstrap_denied",
            status_code=503,
        )

    return {
        "ok": True,
        "already_installed": False,
        "agent_installed": agent_installed(),
        "path_unit_enabled": path_unit_enabled(),
        "message": "Agent installé.",
        "log": log,
    }


def enqueue_panel_update(
    *,
    requested_by: str = "",
    branch: str = "main",
    skip_pull: bool = False,
) -> dict:
    if not agent_installed():
        # Tentative auto-bootstrap (si sudoers déjà en place)
        try:
            bootstrap_update_agent()
        except VZoneAPIException:
            pass
    if not agent_installed():
        raise VZoneAPIException(
            detail=(
                "Agent de mise à jour non installé. Depuis cette page utilisez "
                "« Installer l’agent », ou une fois via SSH : "
                "sudo bash /opt/vzone-src/scripts/install-update-agent.sh"
            ),
            code="update_agent_missing",
            status_code=503,
        )

    src = resolve_src_dir()
    if not src.is_dir():
        raise VZoneAPIException(
            detail=f"Dépôt source introuvable: {src}",
            code="src_missing",
            status_code=400,
        )
    if not (src / "scripts" / "update.sh").is_file():
        raise VZoneAPIException(
            detail=f"scripts/update.sh manquant dans {src}",
            code="update_sh_missing",
            status_code=400,
        )

    if not _jobs_writable():
        raise VZoneAPIException(
            detail=(
                "Répertoire jobs non accessible en écriture "
                f"({update_jobs_dir(create=False)}). "
                "Corrigez les droits : chown -R vzone:vzone /var/lib/vzone/update"
            ),
            code="jobs_not_writable",
            status_code=503,
        )

    if _job_busy():
        raise VZoneAPIException(
            detail="Une mise à jour est déjà en cours.",
            code="update_busy",
            status_code=409,
        )

    jobs = update_jobs_dir(create=True)
    job_id = secrets.token_hex(12)
    request = jobs / f"{job_id}.request"
    payload = {
        "src_dir": str(src),
        "branch": (branch or "main").strip() or "main",
        "skip_pull": bool(skip_pull),
        "requested_by": requested_by,
    }
    tmp = jobs / f"{job_id}.request.tmp"
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(request)

    (jobs / f"{job_id}.status").write_text(
        json.dumps(
            {
                "state": "running",
                "step": "queued",
                "src_dir": str(src),
                "branch": payload["branch"],
                "version_before": get_version(),
            }
        ),
        encoding="utf-8",
    )

    kicked, kick_err = _kick_update_service()
    if not kicked:
        status_path = jobs / f"{job_id}.status"
        st = _read_json(status_path) or {}
        st["kick_warning"] = kick_err or "systemctl start a échoué (attente path unit)"
        status_path.write_text(json.dumps(st), encoding="utf-8")

    return {
        "job_id": job_id,
        "pending": True,
        "message": (
            "Mise à jour démarrée (git fetch + reset hard + update.sh). "
            "L’API peut redémarrer — la page suivra la progression."
        ),
        "src_dir": str(src),
        "branch": payload["branch"],
        "agent_kicked": kicked,
        "kick_error": kick_err if not kicked else "",
    }
