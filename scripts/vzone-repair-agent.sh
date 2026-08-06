#!/usr/bin/env bash
# Agent root : exécute un script repair-* allowlisté (WHM → jobs/*.request)
exec /usr/bin/python3 - "$@" <<'PY'
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

JOBS_DIR = Path(os.environ.get("VZONE_REPAIR_JOBS_DIR", "/var/lib/vzone/repair/jobs"))
DEFAULT_SRC = os.environ.get("VZONE_SRC_DIR", "/opt/vzone-src")

# Doit rester synchronisé avec backend/apps/server_setup/repairs.py
ALLOWED = {
    "smtp": "repair-smtp.sh",
    "dkim": "repair-dkim.sh",
    "roundcube": "repair-roundcube.sh",
    "mail-auth": "repair-mail-auth.sh",
    "mail-reputation": "repair-mail-reputation.sh",
    "frontend": "repair-frontend.sh",
    "api-502": "repair-api-502.sh",
    "panel-404": "repair-panel-404.sh",
    "nginx-500": "repair-nginx-500.sh",
    "domains-403": "repair-domains-403.sh",
    "external-access": "repair-external-access.sh",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chown_vzone(path: Path) -> None:
    try:
        import pwd

        uid = pwd.getpwnam("vzone").pw_uid
        gid = pwd.getpwnam("vzone").pw_gid
        os.chown(path, uid, gid)
    except (KeyError, OSError):
        pass
    try:
        os.chmod(path, 0o640)
    except OSError:
        pass


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    _chown_vzone(path)


def append_log(log: Path, line: str) -> None:
    with log.open("a", encoding="utf-8") as fh:
        fh.write(line)
        if not line.endswith("\n"):
            fh.write("\n")
    _chown_vzone(log)


def process(req: Path) -> None:
    job_id = req.stem
    result = req.with_suffix(".result")
    status = req.with_suffix(".status")
    log = req.with_suffix(".log")
    lock = JOBS_DIR / f"{job_id}.lock"

    if result.exists():
        req.unlink(missing_ok=True)
        return

    try:
        lock.mkdir()
    except FileExistsError:
        if lock.exists() and time.time() - lock.stat().st_mtime > 3600:
            try:
                lock.rmdir()
                lock.mkdir()
            except OSError:
                return
        else:
            return

    script_id = ""
    script_name = ""
    try:
        data = json.loads(req.read_text(encoding="utf-8"))
        script_id = str(data.get("script_id") or "").strip()
        src_dir = Path(str(data.get("src_dir") or DEFAULT_SRC))
        script_name = ALLOWED.get(script_id, "")
        if not script_name:
            raise RuntimeError(f"script_id non autorisé: {script_id!r}")

        script_path = src_dir / "scripts" / script_name
        if not script_path.is_file():
            raise RuntimeError(f"Script introuvable: {script_path}")

        write_json(
            status,
            {
                "state": "running",
                "step": "starting",
                "script_id": script_id,
                "script": script_name,
                "started_at": _now(),
            },
        )
        append_log(log, f"[vzone-repair] job={job_id} script={script_id} ({script_name})")
        append_log(log, f"[vzone-repair] started_at={_now()}")

        write_json(
            status,
            {
                "state": "running",
                "step": "running",
                "script_id": script_id,
                "script": script_name,
                "started_at": _now(),
            },
        )
        append_log(log, f"[vzone-repair] === bash {script_path}")

        proc = subprocess.run(
            ["bash", str(script_path)],
            cwd=str(src_dir),
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
            env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
        )
        if proc.stdout:
            append_log(log, proc.stdout.rstrip("\n"))
        if proc.stderr:
            append_log(log, proc.stderr.rstrip("\n"))
        append_log(log, f"[vzone-repair] exit_code={proc.returncode}")

        ok = proc.returncode == 0
        write_json(
            result,
            {
                "ok": ok,
                "error": "" if ok else f"exit {proc.returncode}",
                "script_id": script_id,
                "script": script_name,
                "exit_code": proc.returncode,
                "finished_at": _now(),
            },
        )
        write_json(
            status,
            {
                "state": "done" if ok else "error",
                "step": "finished" if ok else "failed",
                "script_id": script_id,
                "script": script_name,
            },
        )
        append_log(log, f"[vzone-repair] terminé {'OK' if ok else 'ECHEC'}")
    except Exception as exc:  # noqa: BLE001
        append_log(log, f"[vzone-repair] ERREUR: {exc}")
        write_json(
            result,
            {
                "ok": False,
                "error": str(exc),
                "script_id": script_id,
                "script": script_name,
                "finished_at": _now(),
            },
        )
        write_json(
            status,
            {
                "state": "error",
                "step": "failed",
                "script_id": script_id,
                "script": script_name,
            },
        )
    finally:
        req.unlink(missing_ok=True)
        try:
            lock.rmdir()
        except OSError:
            pass


def main() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    requests = sorted(JOBS_DIR.glob("*.request"), key=lambda p: p.stat().st_mtime)
    for req in requests:
        process(req)


if __name__ == "__main__":
    main()
PY
