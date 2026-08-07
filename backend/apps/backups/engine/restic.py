"""Wrapper Restic — moteur de backup chiffré."""
from __future__ import annotations

import json
import logging
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from django.conf import settings

from apps.backups.engine import CmdResult, run_cmd

logger = logging.getLogger(__name__)

ProgressCb = Callable[[int, str], None]


@dataclass
class SnapshotInfo:
    id: str
    short_id: str = ""
    time: str = ""
    hostname: str = ""
    paths: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


def restic_bin() -> str:
    return str(getattr(settings, "VZONE_RESTIC_BIN", "restic") or "restic")


def restic_env(
    *,
    password: str,
    repository: str,
    rclone_config: Path | None = None,
) -> dict[str, str]:
    env = {
        "RESTIC_PASSWORD": password,
        "RESTIC_REPOSITORY": repository,
        "RESTIC_CACHE_DIR": str(
            Path(getattr(settings, "VZONE_BACKUP_DIR", "/var/lib/vzone/backups")) / "cache"
        ),
    }
    if rclone_config and rclone_config.is_file():
        env["RCLONE_CONFIG"] = str(rclone_config)
    return env


def init_repository(
    *,
    repository: str,
    password: str,
    rclone_config: Path | None = None,
) -> CmdResult:
    env = restic_env(password=password, repository=repository, rclone_config=rclone_config)
    # init est idempotent si déjà initialisé → on tolère "already initialized"
    result = run_cmd([restic_bin(), "init"], env=env, timeout=120)
    if result.ok:
        return result
    if "already initialized" in (result.stderr + result.stdout).lower():
        return CmdResult(returncode=0, stdout=result.stdout, stderr=result.stderr, cmd=result.cmd)
    return result


def backup_paths(
    *,
    repository: str,
    password: str,
    paths: list[str],
    tags: list[str] | None = None,
    host: str | None = None,
    rclone_config: Path | None = None,
    exclude: list[str] | None = None,
    on_progress: ProgressCb | None = None,
) -> tuple[CmdResult, SnapshotInfo | None]:
    if on_progress:
        on_progress(10, "restic backup starting")
    env = restic_env(password=password, repository=repository, rclone_config=rclone_config)
    cmd = [restic_bin(), "backup", "--json"]
    for tag in tags or []:
        cmd.extend(["--tag", tag])
    if host:
        cmd.extend(["--host", host])
    for ex in exclude or []:
        cmd.extend(["--exclude", ex])
    cmd.extend(paths)
    result = run_cmd(cmd, env=env, timeout=int(getattr(settings, "VZONE_BACKUP_TIMEOUT", 7200)))
    if on_progress:
        on_progress(80, "restic backup finished")
    snapshot = _parse_backup_json(result.stdout)
    return result, snapshot


def restore_snapshot(
    *,
    repository: str,
    password: str,
    snapshot_id: str,
    target: Path,
    include_paths: list[str] | None = None,
    rclone_config: Path | None = None,
    on_progress: ProgressCb | None = None,
) -> CmdResult:
    if on_progress:
        on_progress(20, f"restic restore {snapshot_id[:8]}")
    target.mkdir(parents=True, exist_ok=True)
    env = restic_env(password=password, repository=repository, rclone_config=rclone_config)
    cmd = [
        restic_bin(),
        "restore",
        snapshot_id,
        "--target",
        str(target),
    ]
    for p in include_paths or []:
        cmd.extend(["--include", p])
    result = run_cmd(cmd, env=env, timeout=int(getattr(settings, "VZONE_BACKUP_TIMEOUT", 7200)))
    if on_progress:
        on_progress(90, "restic restore done")
    return result


def forget_and_prune(
    *,
    repository: str,
    password: str,
    keep_hourly: int = 0,
    keep_daily: int = 7,
    keep_weekly: int = 4,
    keep_monthly: int = 6,
    tags: list[str] | None = None,
    rclone_config: Path | None = None,
) -> CmdResult:
    env = restic_env(password=password, repository=repository, rclone_config=rclone_config)
    cmd = [restic_bin(), "forget", "--prune", "--json"]
    if keep_hourly > 0:
        cmd.extend(["--keep-hourly", str(keep_hourly)])
    if keep_daily > 0:
        cmd.extend(["--keep-daily", str(keep_daily)])
    if keep_weekly > 0:
        cmd.extend(["--keep-weekly", str(keep_weekly)])
    if keep_monthly > 0:
        cmd.extend(["--keep-monthly", str(keep_monthly)])
    for tag in tags or []:
        cmd.extend(["--tag", tag])
    return run_cmd(cmd, env=env, timeout=3600)


def list_snapshots(
    *,
    repository: str,
    password: str,
    rclone_config: Path | None = None,
    tags: list[str] | None = None,
) -> list[SnapshotInfo]:
    env = restic_env(password=password, repository=repository, rclone_config=rclone_config)
    cmd = [restic_bin(), "snapshots", "--json"]
    for tag in tags or []:
        cmd.extend(["--tag", tag])
    result = run_cmd(cmd, env=env, timeout=120)
    if not result.ok:
        return []
    try:
        data = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    out: list[SnapshotInfo] = []
    for item in data if isinstance(data, list) else []:
        out.append(
            SnapshotInfo(
                id=str(item.get("id") or ""),
                short_id=str(item.get("short_id") or ""),
                time=str(item.get("time") or ""),
                hostname=str(item.get("hostname") or ""),
                paths=list(item.get("paths") or []),
                tags=list(item.get("tags") or []),
                summary=dict(item.get("summary") or {}),
            )
        )
    return out


def stats(
    *,
    repository: str,
    password: str,
    rclone_config: Path | None = None,
) -> dict[str, Any]:
    env = restic_env(password=password, repository=repository, rclone_config=rclone_config)
    result = run_cmd([restic_bin(), "stats", "--json", "latest"], env=env, timeout=300)
    if not result.ok:
        return {}
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def generate_password() -> str:
    return secrets.token_urlsafe(32)


def _parse_backup_json(stdout: str) -> SnapshotInfo | None:
    """Parse la dernière ligne JSON type=summary / exit de restic --json."""
    last_summary: dict[str, Any] | None = None
    snapshot_id = ""
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("message_type") == "summary" or obj.get("message_type") == "exit":
            last_summary = obj
            snapshot_id = str(obj.get("snapshot_id") or obj.get("id") or snapshot_id)
    if not last_summary and not snapshot_id:
        return None
    summary = last_summary or {}
    return SnapshotInfo(
        id=snapshot_id or str(summary.get("snapshot_id") or ""),
        short_id=(snapshot_id or "")[:8],
        summary={
            "total_bytes_processed": summary.get("total_bytes_processed", 0),
            "data_added": summary.get("data_added", 0),
            "files_new": summary.get("files_new", 0),
            "files_changed": summary.get("files_changed", 0),
            "files_unmodified": summary.get("files_unmodified", 0),
        },
    )
