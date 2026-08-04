#!/usr/bin/env bash
# Agent root : traite /var/lib/vzone/hostname/jobs/*.request
exec /usr/bin/python3 - "$@" <<'PY'
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

JOBS_DIR = Path(os.environ.get("VZONE_HOSTNAME_JOBS_DIR", "/var/lib/vzone/hostname/jobs"))
SET_BIN = os.environ.get("VZONE_HOSTNAME_SET_BIN", "/usr/local/sbin/vzone-hostname-set")


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
        hostname = str(data.get("hostname") or "").strip()
        apply_mail = "1" if data.get("apply_mail", True) else "0"
        public_ip = str(data.get("public_ip") or "").strip()
        if not hostname:
            write_result(result, {"ok": False, "error": "Job invalide (hostname)"})
            return

        cmd = [SET_BIN, hostname, apply_mail, public_ip]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=120)
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            write_result(
                result,
                {
                    "ok": False,
                    "error": err or out or f"exit {proc.returncode}",
                    "stdout": out[-2000:],
                },
            )
            return
        # Prefer JSON line from script if present
        meta = {"ok": True, "hostname": hostname}
        for line in reversed(out.splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    meta = json.loads(line)
                    break
                except json.JSONDecodeError:
                    pass
        if "ok" not in meta:
            meta["ok"] = True
        write_result(result, meta)
        # Redémarrage différé pour laisser l'API renvoyer la réponse WHM
        subprocess.Popen(
            ["bash", "-lc", "sleep 2; systemctl restart vzone-api"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
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


def main() -> int:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    requests = sorted(JOBS_DIR.glob("*.request"), key=lambda p: p.stat().st_mtime)
    for req in requests:
        process(req)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY
