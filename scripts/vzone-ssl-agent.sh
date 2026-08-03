#!/usr/bin/env bash
# Lance l'agent Python (jobs Let's Encrypt sans sudo / NoNewPrivileges).
exec /usr/bin/python3 - "$@" <<'PY'
"""Traite /var/lib/vzone/ssl/jobs/*.request → *.result (root)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

JOBS_DIR = Path(os.environ.get("VZONE_SSL_JOBS_DIR", "/var/lib/vzone/ssl/jobs"))
ISSUE_BIN = os.environ.get("VZONE_SSL_ISSUE_BIN", "/usr/local/sbin/vzone-ssl-issue")


def write_result(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        os.chown(path, 0, 0)  # will fix below
    except OSError:
        pass
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
        # lock trop vieux (>10 min) → reprendre
        if lock.exists() and time.time() - lock.stat().st_mtime > 600:
            try:
                lock.rmdir()
                lock.mkdir()
            except OSError:
                return
        else:
            return

    try:
        data = json.loads(req.read_text(encoding="utf-8"))
        domain = str(data.get("domain") or "").strip()
        email = str(data.get("email") or "").strip()
        extras = [str(x).strip() for x in (data.get("extras") or []) if str(x).strip()]
        if not domain or not email:
            write_result(result, {"ok": False, "error": "Job invalide (domain/email)"})
            return

        cmd = [ISSUE_BIN, domain, email, *extras]
        # stdout non bufferisé : le JSON succès est émis avant le reload Nginx
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        assert proc.stdout is not None
        meta: dict | None = None
        stdout_lines: list[str] = []
        for line in proc.stdout:
            stdout_lines.append(line)
            stripped = line.strip()
            if stripped.startswith("{") and meta is None:
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict) and parsed.get("cert_path"):
                    meta = {"ok": True, "domain": domain, **parsed}
                    # Notifier l'API avant le reload Nginx (évite 502 panel)
                    write_result(result, meta)
        rc = proc.wait()
        if meta is not None:
            return
        if rc != 0:
            err = ("".join(stdout_lines) or f"exit {rc}").strip()
            write_result(
                result,
                {"ok": False, "error": err[-2000:], "domain": domain},
            )
            return
        # Succès sans JSON (ne devrait pas arriver)
        write_result(result, {"ok": True, "domain": domain})
    except Exception as exc:  # noqa: BLE001
        write_result(result, {"ok": False, "error": str(exc)})
    finally:
        req.unlink(missing_ok=True)
        try:
            lock.rmdir()
        except OSError:
            pass


def main() -> int:
    if os.geteuid() != 0:
        print("Root requis", file=sys.stderr)
        return 1
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    for req in sorted(JOBS_DIR.glob("*.request")):
        process(req)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY
