"""Scripts de réparation WHM (allowlist + jobs via agent root)."""
from __future__ import annotations

import json
import secrets
import subprocess
from pathlib import Path

from django.conf import settings

from apps.core.exceptions import VZoneAPIException
from apps.server_setup.panel_update import default_src_dir


# Scripts manuels / d'urgence — pas le bootstrap d'installation initiale.
# id → métadonnées + nom fichier (doit matcher vzone-repair-agent.sh)
REPAIR_CATALOG: dict[str, dict] = {
    "smtp": {
        "script": "repair-smtp.sh",
        "title": "Réparer SMTP (Roundcube)",
        "description": "Coupe les milters DKIM et rétablit l’envoi webmail (priorité SMTP).",
        "category": "mail",
        "risk": "safe",
    },
    "dkim": {
        "script": "repair-dkim.sh",
        "title": "Activer / réparer DKIM",
        "description": "Active la signature DKIM après test AUTH ; rollback auto si SMTP casse.",
        "category": "mail",
        "risk": "caution",
    },
    "roundcube": {
        "script": "repair-roundcube.sh",
        "title": "Réparer Roundcube",
        "description": "Régénère la config PHP Roundcube (Oops / config cassée).",
        "category": "mail",
        "risk": "safe",
    },
    "mail-auth": {
        "script": "repair-mail-auth.sh",
        "title": "Réparer auth mail",
        "description": "Corrige Dovecot / maps utilisateurs (login Roundcube UNAVAILABLE).",
        "category": "mail",
        "risk": "safe",
    },
    "mail-reputation": {
        "script": "repair-mail-reputation.sh",
        "title": "Réparer réputation mail",
        "description": "SPF / DKIM DNS / tables OpenDKIM pour tous les domaines mail.",
        "category": "mail",
        "risk": "safe",
    },
    "frontend": {
        "script": "repair-frontend.sh",
        "title": "Réparer frontend panel",
        "description": "Rebuild npm du frontend (dist manquant / UI 404).",
        "category": "panel",
        "risk": "safe",
    },
    "api-502": {
        "script": "repair-api-502.sh",
        "title": "Réparer API 502",
        "description": "Relance gunicorn / socket API derrière nginx.",
        "category": "panel",
        "risk": "safe",
    },
    "panel-404": {
        "script": "repair-panel-404.sh",
        "title": "Réparer panel 404",
        "description": "Corrige nginx + frontend pour le panel inaccessible.",
        "category": "panel",
        "risk": "safe",
    },
    "nginx-500": {
        "script": "repair-nginx-500.sh",
        "title": "Réparer nginx 500",
        "description": "Diagnostique et corrige les erreurs 500 nginx.",
        "category": "web",
        "risk": "safe",
    },
    "domains-403": {
        "script": "repair-domains-403.sh",
        "title": "Réparer domaines 403",
        "description": "Permissions home / public_html / ACL (403 Forbidden sites).",
        "category": "web",
        "risk": "safe",
    },
    "external-access": {
        "script": "repair-external-access.sh",
        "title": "Réparer accès externe",
        "description": "Ouvre HTTP/HTTPS/DNS (UFW / firewalld / règles bloquantes).",
        "category": "network",
        "risk": "caution",
    },
}


def repair_jobs_dir() -> Path:
    root = Path(getattr(settings, "VZONE_DATA_ROOT", "/var/lib/vzone")) / "repair" / "jobs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def agent_installed() -> bool:
    return Path("/usr/local/sbin/vzone-repair-agent").is_file()


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


def _job_busy() -> bool:
    jobs = repair_jobs_dir()
    if any(jobs.glob("*.request")) or any(jobs.glob("*.lock")):
        return True
    for status_path in jobs.glob("*.status"):
        data = _read_json(status_path) or {}
        if data.get("state") == "running" and not (jobs / f"{status_path.stem}.result").is_file():
            return True
    return False


def list_catalog(*, src: Path | None = None) -> list[dict]:
    src = src or default_src_dir()
    items: list[dict] = []
    for sid, meta in REPAIR_CATALOG.items():
        script_path = src / "scripts" / meta["script"]
        items.append(
            {
                "id": sid,
                "title": meta["title"],
                "description": meta["description"],
                "category": meta["category"],
                "risk": meta["risk"],
                "script": meta["script"],
                "available": script_path.is_file(),
            }
        )
    return items


def list_recent_jobs(*, limit: int = 10) -> list[dict]:
    jobs = repair_jobs_dir()
    items: list[dict] = []
    for path in sorted(jobs.glob("*.result"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        data = _read_json(path) or {}
        items.append(
            {
                "job_id": path.stem,
                "ok": bool(data.get("ok")),
                "error": data.get("error") or "",
                "script_id": data.get("script_id") or "",
                "script": data.get("script") or "",
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
                    "script_id": data.get("script_id") or "",
                    "script": data.get("script") or "",
                    "started_at": data.get("started_at") or "",
                },
            )
    return items[:limit]


def repairs_overview() -> dict:
    src = default_src_dir()
    return {
        "src_dir": str(src),
        "src_exists": src.is_dir(),
        "agent_installed": agent_installed(),
        "busy": _job_busy(),
        "scripts": list_catalog(src=src),
        "recent_jobs": list_recent_jobs(),
    }


def get_repair_job_status(job_id: str) -> dict:
    job_id = (job_id or "").strip()
    if not job_id or "/" in job_id or ".." in job_id:
        raise VZoneAPIException(detail="job_id invalide.", code="invalid_job", status_code=400)

    jobs = repair_jobs_dir()
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
            "script_id": result.get("script_id") or status.get("script_id") or "",
            "script": result.get("script") or status.get("script") or "",
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
            "script_id": status.get("script_id") or "",
            "script": status.get("script") or "",
            "step": status.get("step") or "queued",
            "started_at": status.get("started_at") or "",
            "log": log,
        }

    raise VZoneAPIException(
        detail="Job de réparation introuvable.",
        code="job_not_found",
        status_code=404,
    )


def enqueue_repair(*, script_id: str, requested_by: str = "") -> dict:
    script_id = (script_id or "").strip()
    meta = REPAIR_CATALOG.get(script_id)
    if not meta:
        raise VZoneAPIException(
            detail=f"Script inconnu: {script_id}",
            code="unknown_script",
            status_code=400,
        )

    if not agent_installed():
        raise VZoneAPIException(
            detail=(
                "Agent de réparation non installé. Une fois via SSH : "
                "sudo bash /opt/vzone-src/scripts/install-repair-agent.sh"
            ),
            code="repair_agent_missing",
            status_code=503,
        )

    src = default_src_dir()
    script_path = src / "scripts" / meta["script"]
    if not script_path.is_file():
        raise VZoneAPIException(
            detail=f"Fichier absent: {script_path}",
            code="script_missing",
            status_code=400,
        )

    if _job_busy():
        raise VZoneAPIException(
            detail="Une réparation est déjà en cours. Attendez la fin.",
            code="repair_busy",
            status_code=409,
        )

    jobs = repair_jobs_dir()
    job_id = secrets.token_hex(12)
    request = jobs / f"{job_id}.request"
    payload = {
        "script_id": script_id,
        "src_dir": str(src),
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
                "script_id": script_id,
                "script": meta["script"],
            }
        ),
        encoding="utf-8",
    )

    try:
        subprocess.run(
            ["systemctl", "start", "vzone-repair-job.service"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return {
        "job_id": job_id,
        "pending": True,
        "script_id": script_id,
        "script": meta["script"],
        "title": meta["title"],
        "message": f"Réparation démarrée : {meta['title']}",
    }
