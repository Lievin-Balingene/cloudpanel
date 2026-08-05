#!/usr/bin/env bash
# Agent root : git pull + update.sh depuis /var/lib/vzone/update/jobs/*.request
exec /usr/bin/python3 - "$@" <<'PY'
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

JOBS_DIR = Path(os.environ.get("VZONE_UPDATE_JOBS_DIR", "/var/lib/vzone/update/jobs"))
DEFAULT_SRC = os.environ.get("VZONE_SRC_DIR", "/opt/vzone-src")
GLOBAL_LOCK = JOBS_DIR.parent / ".lock"


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


def read_version(src: Path) -> str:
    vf = src / "VERSION"
    if vf.is_file():
        return vf.read_text(encoding="utf-8").strip()
    return ""


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

    try:
        if GLOBAL_LOCK.exists():
            age = time.time() - GLOBAL_LOCK.stat().st_mtime
            if age < 3600:
                write_json(
                    result,
                    {
                        "ok": False,
                        "error": "Une mise à jour est déjà en cours.",
                        "finished_at": _now(),
                    },
                )
                return
            try:
                GLOBAL_LOCK.unlink()
            except OSError:
                pass
        GLOBAL_LOCK.write_text(job_id, encoding="utf-8")
        _chown_vzone(GLOBAL_LOCK)

        data = json.loads(req.read_text(encoding="utf-8"))
        src_dir = Path(str(data.get("src_dir") or DEFAULT_SRC)).resolve()
        branch = str(data.get("branch") or "main").strip() or "main"
        skip_pull = bool(data.get("skip_pull", False))

        if not src_dir.is_dir():
            write_json(
                result,
                {
                    "ok": False,
                    "error": f"Dépôt introuvable: {src_dir}",
                    "finished_at": _now(),
                },
            )
            return

        update_sh = src_dir / "scripts" / "update.sh"
        if not update_sh.is_file():
            write_json(
                result,
                {
                    "ok": False,
                    "error": f"scripts/update.sh introuvable dans {src_dir}",
                    "finished_at": _now(),
                },
            )
            return

        version_before = read_version(src_dir)
        write_json(
            status,
            {
                "state": "running",
                "step": "starting",
                "src_dir": str(src_dir),
                "branch": branch,
                "version_before": version_before,
                "started_at": _now(),
            },
        )
        if log.exists():
            log.unlink()
        append_log(log, f"[vzone-update] job={job_id} started_at={_now()}")
        append_log(log, f"[vzone-update] src={src_dir} branch={branch}")

        def run_step(step: str, cmd: list[str], *, cwd: Path | None = None) -> int:
            started_at = _now()
            try:
                prev = json.loads(status.read_text(encoding="utf-8"))
                started_at = prev.get("started_at") or started_at
            except (OSError, json.JSONDecodeError):
                pass
            write_json(
                status,
                {
                    "state": "running",
                    "step": step,
                    "src_dir": str(src_dir),
                    "branch": branch,
                    "version_before": version_before,
                    "started_at": started_at,
                    "updated_at": _now(),
                },
            )
            append_log(log, f"[vzone-update] === {step}: {' '.join(cmd)}")
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd or src_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                append_log(log, line.rstrip("\n"))
            return proc.wait(timeout=3600)

        if not skip_pull:
            # Fetch + reset soft approach: pull current branch
            rc = run_step(
                "git_pull",
                ["git", "-C", str(src_dir), "pull", "--ff-only", "origin", branch],
            )
            if rc != 0:
                # Fallback without specifying remote/branch
                rc = run_step("git_pull_fallback", ["git", "-C", str(src_dir), "pull", "--ff-only"])
            if rc != 0:
                write_json(
                    result,
                    {
                        "ok": False,
                        "error": f"git pull a échoué (exit {rc})",
                        "version_before": version_before,
                        "finished_at": _now(),
                    },
                )
                return

        version_mid = read_version(src_dir)
        append_log(log, f"[vzone-update] VERSION après pull: {version_mid or '?'}")

        rc = run_step("update_sh", ["bash", str(update_sh)], cwd=src_dir)
        version_after = read_version(src_dir)
        if rc != 0:
            write_json(
                result,
                {
                    "ok": False,
                    "error": f"update.sh a échoué (exit {rc})",
                    "version_before": version_before,
                    "version_after": version_after,
                    "finished_at": _now(),
                },
            )
            return

        append_log(log, f"[vzone-update] terminé OK version={version_after}")
        write_json(
            result,
            {
                "ok": True,
                "version_before": version_before,
                "version_after": version_after,
                "src_dir": str(src_dir),
                "branch": branch,
                "finished_at": _now(),
            },
        )
        write_json(
            status,
            {
                "state": "done",
                "step": "finished",
                "version_before": version_before,
                "version_after": version_after,
                "finished_at": _now(),
            },
        )
    except Exception as exc:  # noqa: BLE001
        write_json(result, {"ok": False, "error": str(exc), "finished_at": _now()})
        try:
            append_log(log, f"[vzone-update] ERREUR: {exc}")
        except OSError:
            pass
    finally:
        try:
            req.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            lock.rmdir()
        except OSError:
            pass
        try:
            if GLOBAL_LOCK.is_file() and GLOBAL_LOCK.read_text(encoding="utf-8").strip() == job_id:
                GLOBAL_LOCK.unlink(missing_ok=True)
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
