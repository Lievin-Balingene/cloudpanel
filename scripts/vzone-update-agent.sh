#!/usr/bin/env bash
# Agent root : sync git (fetch + reset hard) + update.sh depuis /var/lib/vzone/update/jobs/*.request
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
VZONE_ROOT = Path(os.environ.get("VZONE_ROOT", "/opt/vzone"))


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


def read_version(*roots: Path) -> str:
    for root in roots:
        vf = root / "VERSION"
        if vf.is_file():
            try:
                return vf.read_text(encoding="utf-8").strip()
            except OSError:
                continue
    return ""


def ensure_safe_directory(src: Path, log: Path) -> None:
    """Évite « fatal: detected dubious ownership » quand root lit un dépôt non-root."""
    path = str(src)
    for scope in ("--system", "--global"):
        try:
            subprocess.run(
                ["git", "config", scope, "--add", "safe.directory", path],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            pass
    try:
        subprocess.run(
            ["git", "-C", path, "config", "safe.directory", path],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass
    append_log(log, f"[vzone-update] safe.directory OK pour {path}")


def sync_git(src: Path, branch: str, *, run_step, log: Path) -> tuple[bool, str]:
    """
    Aligne le dépôt source exactement sur origin/<branch>.
    Plus fiable que « git pull --ff-only » (arbre sale, commits locaux, detached HEAD).
    """
    git = ["git", "-C", str(src)]

    probe = subprocess.run(
        [*git, "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if probe.returncode != 0:
        return False, f"Pas un dépôt git: {src}"

    for unlock_cmd in (
        [*git, "merge", "--abort"],
        [*git, "rebase", "--abort"],
        [*git, "cherry-pick", "--abort"],
    ):
        subprocess.run(unlock_cmd, capture_output=True, text=True, check=False, timeout=30)

    rc = run_step("git_fetch", [*git, "fetch", "--prune", "--tags", "origin"])
    if rc != 0:
        rc = run_step("git_fetch_fallback", [*git, "fetch", "origin"])
    if rc != 0:
        return False, f"git fetch a échoué (exit {rc})"

    remote_ref = f"origin/{branch}"
    ref_ok = subprocess.run(
        [*git, "rev-parse", "--verify", remote_ref],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if ref_ok.returncode != 0:
        resolved = False
        for alt in ("main", "master"):
            if alt == branch:
                continue
            alt_ref = f"origin/{alt}"
            alt_ok = subprocess.run(
                [*git, "rev-parse", "--verify", alt_ref],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if alt_ok.returncode == 0:
                append_log(log, f"[vzone-update] branche {branch} absente → bascule {alt}")
                remote_ref = alt_ref
                branch = alt
                resolved = True
                break
        if not resolved:
            return False, f"Branche distante introuvable: origin/{branch}"

    rc = run_step("git_checkout", [*git, "checkout", "-B", branch, remote_ref])
    if rc != 0:
        rc = run_step("git_checkout_local", [*git, "checkout", branch])
        if rc != 0:
            return False, f"git checkout {branch} a échoué (exit {rc})"

    rc = run_step("git_reset", [*git, "reset", "--hard", remote_ref])
    if rc != 0:
        return False, f"git reset --hard {remote_ref} a échoué (exit {rc})"

    # Nettoyer fichiers non suivis qui peuvent casser rsync/build
    run_step(
        "git_clean",
        [*git, "clean", "-fd", "-e", ".env", "-e", ".data", "-e", ".logs"],
    )

    head = subprocess.run(
        [*git, "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    tip = (head.stdout or "").strip() or "?"
    return True, f"{remote_ref} @ {tip}"


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
        # Consommer la requête tout de suite (évite re-trigger PathExistsGlob / 2e start)
        try:
            req.unlink(missing_ok=True)
        except OSError:
            pass

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

        version_before = read_version(src_dir, VZONE_ROOT)
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
            env = os.environ.copy()
            env.setdefault("GIT_TERMINAL_PROMPT", "0")
            env.setdefault("DEBIAN_FRONTEND", "noninteractive")
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd or src_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                append_log(log, line.rstrip("\n"))
            return int(proc.wait())

        ensure_safe_directory(src_dir, log)

        if not skip_pull:
            ok, detail = sync_git(src_dir, branch, run_step=run_step, log=log)
            append_log(log, f"[vzone-update] sync git: {detail}")
            if not ok:
                write_json(
                    result,
                    {
                        "ok": False,
                        "error": detail,
                        "version_before": version_before,
                        "finished_at": _now(),
                    },
                )
                write_json(
                    status,
                    {
                        "state": "error",
                        "step": "failed",
                        "error": detail,
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
                    "error": f"scripts/update.sh manquant après sync: {src_dir}",
                    "version_before": version_before,
                    "finished_at": _now(),
                },
            )
            return

        version_mid = read_version(src_dir)
        append_log(log, f"[vzone-update] VERSION après sync: {version_mid or '?'}")

        try:
            update_sh.chmod(update_sh.stat().st_mode | 0o111)
        except OSError:
            pass

        rc = run_step("update_sh", ["bash", str(update_sh)], cwd=src_dir)
        version_after = read_version(VZONE_ROOT, src_dir)

        install_agent = src_dir / "scripts" / "install-update-agent.sh"
        if install_agent.is_file():
            run_step("reinstall_agent", ["bash", str(install_agent)], cwd=src_dir)

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
            write_json(
                status,
                {
                    "state": "error",
                    "step": "failed",
                    "version_before": version_before,
                    "version_after": version_after,
                    "finished_at": _now(),
                },
            )
            return

        installed = VZONE_ROOT / "VERSION"
        if version_mid and installed.is_file():
            try:
                installed_ver = installed.read_text(encoding="utf-8").strip()
            except OSError:
                installed_ver = ""
            if installed_ver and installed_ver != version_mid:
                append_log(
                    log,
                    f"[vzone-update] ALERTE: VERSION installée ({installed_ver}) "
                    f"≠ source ({version_mid})",
                )

        append_log(log, f"[vzone-update] terminé OK {version_before} → {version_after}")
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
