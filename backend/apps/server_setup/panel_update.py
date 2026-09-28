"""Mise à jour du panel depuis WHM (git sync + update.sh via agent root)."""
from __future__ import annotations

import json
import secrets
import shutil
import subprocess
import time
from pathlib import Path

from django.conf import settings

from apps.core.exceptions import VZoneAPIException
from vzone import get_version


def update_jobs_dir() -> Path:
    root = Path(getattr(settings, "VZONE_DATA_ROOT", "/var/lib/vzone")) / "update" / "jobs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def default_src_dir() -> Path:
    return Path(getattr(settings, "VZONE_SRC_DIR", "/opt/vzone-src"))


def agent_installed() -> bool:
    return Path("/usr/local/sbin/vzone-update-agent").is_file()


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
    jobs = update_jobs_dir()
    # Nettoyer locks / request périmés (>1h) pour ne pas bloquer à jamais
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


def _kick_update_service() -> tuple[bool, str]:
    """Démarre l'agent root (sudoers NOPASSWD ou path unit)."""
    systemctl = shutil.which("systemctl") or "/bin/systemctl"
    attempts: list[list[str]] = [
        ["sudo", "-n", systemctl, "start", "vzone-update-job.service"],
        ["sudo", "-n", systemctl, "start", "vzone-update-job.path"],
        [systemctl, "start", "vzone-update-job.service"],
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
    jobs = update_jobs_dir()
    items: list[dict] = []
    paths = sorted(jobs.glob("*.result"), key=lambda p: p.stat().st_mtime, reverse=True)
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
    for status_path in sorted(jobs.glob("*.status"), key=lambda p: p.stat().st_mtime, reverse=True):
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
    src = default_src_dir()
    src_version = ""
    if (src / "VERSION").is_file():
        try:
            src_version = (src / "VERSION").read_text(encoding="utf-8").strip()
        except OSError:
            src_version = ""
    git_info = _git_src_info(src)
    return {
        "version": get_version(),
        "src_dir": str(src),
        "src_exists": src.is_dir(),
        "src_version": src_version,
        "agent_installed": agent_installed(),
        "busy": _job_busy(),
        "recent_jobs": list_recent_jobs(),
        **git_info,
    }


def get_job_status(job_id: str) -> dict:
    job_id = (job_id or "").strip()
    if not job_id or "/" in job_id or ".." in job_id:
        raise VZoneAPIException(detail="job_id invalide.", code="invalid_job", status_code=400)

    jobs = update_jobs_dir()
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


def enqueue_panel_update(
    *,
    requested_by: str = "",
    branch: str = "main",
    skip_pull: bool = False,
) -> dict:
    if not agent_installed():
        raise VZoneAPIException(
            detail=(
                "Agent de mise à jour non installé. Une fois via SSH : "
                "sudo bash /opt/vzone-src/scripts/install-update-agent.sh"
            ),
            code="update_agent_missing",
            status_code=503,
        )

    src = default_src_dir()
    if not src.is_dir():
        raise VZoneAPIException(
            detail=f"Dépôt source introuvable: {src}",
            code="src_missing",
            status_code=400,
        )

    if _job_busy():
        raise VZoneAPIException(
            detail="Une mise à jour est déjà en cours.",
            code="update_busy",
            status_code=409,
        )

    jobs = update_jobs_dir()
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
        # Le path unit peut encore déclencher ; on note l'avertissement dans le status
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
