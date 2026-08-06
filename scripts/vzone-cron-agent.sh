#!/usr/bin/env bash
# Agent root : installe /etc/cron.d/vzone-<user> depuis /var/lib/vzone/cron/jobs/*.request
exec /usr/bin/python3 - "$@" <<'PY'
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

JOBS_DIR = Path(os.environ.get("VZONE_CRON_JOBS_DIR", "/var/lib/vzone/cron/jobs"))
CRON_D = Path(os.environ.get("VZONE_CRON_D_DIR", "/etc/cron.d"))
SAFE_NAME = re.compile(r"^vzone-[a-z][a-z0-9_-]{1,31}$")
SAFE_USER = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")


def write_result(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        import pwd

        uid = pwd.getpwnam("vzone").pw_uid
        gid = pwd.getpwnam("vzone").pw_gid
        os.chown(path, uid, gid)
    except (KeyError, OSError):
        pass
    os.chmod(path, 0o640)


def process(req: Path) -> None:
    job_id = req.stem
    result = req.with_suffix(".result")
    lock = JOBS_DIR / f"{job_id}.lock"
    if result.exists():
        req.unlink(missing_ok=True)
        return
    try:
        lock.mkdir()
    except FileExistsError:
        if lock.exists() and time.time() - lock.stat().st_mtime > 300:
            try:
                lock.rmdir()
                lock.mkdir()
            except OSError:
                return
        else:
            return

    try:
        data = json.loads(req.read_text(encoding="utf-8"))
        username = str(data.get("username") or "").strip().lower()
        filename = str(data.get("filename") or f"vzone-{username}").strip()
        content = str(data.get("content") or "")
        home = str(data.get("home") or "")

        if not SAFE_USER.match(username) or not SAFE_NAME.match(filename):
            write_result(result, {"ok": False, "error": "username/filename invalide"})
            return
        if not content.strip():
            write_result(result, {"ok": False, "error": "contenu vide"})
            return
        # Sécurité : refuser path traversal / noms suspects
        if "/" in filename or ".." in filename:
            write_result(result, {"ok": False, "error": "filename invalide"})
            return

        # Chaque ligne active doit tourner sous le username du compte (anti escalade)
        for raw in content.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 7:
                write_result(result, {"ok": False, "error": f"ligne cron invalide: {line[:80]}"})
                return
            run_user = parts[5]
            if run_user != username:
                write_result(
                    result,
                    {
                        "ok": False,
                        "error": f"utilisateur cron refusé ({run_user} != {username})",
                    },
                )
                return
            if run_user in {"root", "vzone", "www-data", "nobody"}:
                write_result(result, {"ok": False, "error": f"utilisateur privilégié interdit: {run_user}"})
                return

        target = CRON_D / filename
        # Assurer le dossier logs du compte
        if home.startswith("/home/") and ".." not in home:
            logs = Path(home) / "logs"
            try:
                logs.mkdir(parents=True, exist_ok=True)
                # ACL déjà géré par le panel ; best-effort chmod
                os.chmod(logs, 0o755)
            except OSError:
                pass

        tmp = target.with_suffix(".tmp")
        tmp.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
        os.chmod(tmp, 0o644)
        tmp.replace(target)

        write_result(
            result,
            {
                "ok": True,
                "path": str(target),
                "username": username,
                "bytes": len(content),
            },
        )
    except Exception as exc:  # noqa: BLE001
        write_result(result, {"ok": False, "error": str(exc)})
    finally:
        try:
            req.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            lock.rmdir()
        except OSError:
            pass


def main() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    for req in sorted(JOBS_DIR.glob("*.request")):
        process(req)


if __name__ == "__main__":
    main()
PY
