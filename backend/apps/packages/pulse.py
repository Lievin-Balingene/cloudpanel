"""V-zone Pulse — Resource Governor (cgroups v2 / systemd slices par compte)."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.accounts.models import User
from apps.core.exceptions import VZoneAPIException

logger = logging.getLogger(__name__)

HELPER = Path("/usr/local/sbin/vzone-resourcectl")


def _jail_name(user: User) -> str:
    """Nom OS du compte (aligné linux_users.jail_username_for, sans importer pwd hors Linux)."""
    raw = (getattr(user, "system_username", None) or getattr(user, "username", None) or "user")
    name = str(raw).strip().lower()
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        return "user"
    return name


def provision_mode() -> str:
    mode = getattr(settings, "VZONE_PULSE_MODE", "auto").lower()
    if mode not in {"auto", "live", "mock"}:
        mode = "auto"
    if mode == "auto":
        if HELPER.is_file() or shutil.which("systemctl"):
            return "live"
        return "mock"
    return mode


def _limits_from_user(user: User) -> dict[str, int]:
    quota = getattr(user, "quota", None)
    package = None
    try:
        from apps.packages.models import PackageAssignment

        assignment = PackageAssignment.objects.filter(user=user).select_related("package").first()
        if assignment:
            package = assignment.package
    except Exception:  # noqa: BLE001
        package = None

    cpu = int(getattr(quota, "cpu_millicores", 0) or 0) if quota else 1000
    ram = int(getattr(quota, "ram_mb", 0) or 0) if quota else 1024
    tasks = 100
    inodes = 200000
    if package:
        if getattr(package, "unlimited_cpu", False):
            cpu = 0
        else:
            cpu = int(package.cpu_millicores or cpu)
        if getattr(package, "unlimited_ram", False):
            ram = 0
        else:
            ram = int(package.ram_mb or ram)
        tasks = int(package.max_processes or package.max_nproc or tasks)
        inodes = int(package.inode_limit or inodes)
    if quota and getattr(quota, "unlimited_cpu", False):
        cpu = 0
    if quota and getattr(quota, "unlimited_ram", False):
        ram = 0
    if quota and hasattr(quota, "inode_limit") and quota.inode_limit:
        inodes = int(quota.inode_limit)
    if quota and hasattr(quota, "max_processes") and quota.max_processes:
        tasks = int(quota.max_processes)

    # IOWeight : proportionnel au CPU (50–1000)
    io_weight = 100
    if cpu > 0:
        io_weight = max(50, min(1000, cpu // 10))

    return {
        "cpu_millicores": cpu,
        "memory_mb": ram,
        "tasks": tasks,
        "io_weight": io_weight,
        "inode_limit": inodes,
    }


def _run(args: list[str], *, timeout: int = 60) -> dict[str, Any]:
    if provision_mode() == "mock":
        return _mock(args)

    cmd = ["sudo", "-n", str(HELPER), *args]
    if not HELPER.is_file():
        src = Path(getattr(settings, "VZONE_SRC_ROOT", "/opt/vzone-src")) / "scripts" / "vzone-resourcectl.sh"
        if src.is_file():
            cmd = ["sudo", "-n", "bash", str(src), *args]
        else:
            raise VZoneAPIException(
                detail="Helper Pulse absent — sudo bash scripts/ensure-mkhome-sudoers.sh",
                code="pulse_helper_missing",
                status_code=503,
            )
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise VZoneAPIException(
            detail=f"Pulse: {exc}",
            code="pulse_failed",
            status_code=502,
        ) from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        raise VZoneAPIException(
            detail=f"Pulse: {err[:400]}",
            code="pulse_failed",
            status_code=502,
            extra={"stderr": err[:2000]},
        )
    out = (proc.stdout or "").strip()
    if not out:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"raw": out}


def _mock(args: list[str]) -> dict[str, Any]:
    root = Path(getattr(settings, "VZONE_DATA_ROOT", "/tmp/vzone")) / "pulse" / "meta"
    root.mkdir(parents=True, exist_ok=True)
    action = args[0] if args else "status"
    if action == "apply":
        user = args[1]
        meta = {
            "user": user,
            "slice": f"vz-pulse-{user}.slice",
            "cpu_millicores": 1000,
            "memory_mb": 1024,
            "tasks": 100,
            "io_weight": 100,
            "mock": True,
        }
        # parse flags
        i = 2
        while i < len(args):
            if args[i] == "--cpu-millicores" and i + 1 < len(args):
                meta["cpu_millicores"] = int(args[i + 1])
                i += 2
            elif args[i] == "--memory-mb" and i + 1 < len(args):
                meta["memory_mb"] = int(args[i + 1])
                i += 2
            elif args[i] == "--tasks" and i + 1 < len(args):
                meta["tasks"] = int(args[i + 1])
                i += 2
            elif args[i] == "--io-weight" and i + 1 < len(args):
                meta["io_weight"] = int(args[i + 1])
                i += 2
            else:
                i += 1
        (root / f"{user}.json").write_text(json.dumps(meta), encoding="utf-8")
        return {
            "user": user,
            "slice": meta["slice"],
            "memory_current_bytes": 0,
            "memory_max_bytes": meta["memory_mb"] * 1024 * 1024,
            "tasks_current": 0,
            "cpu_usage_usec": 0,
            "disk_bytes": 0,
            "inodes_used": 0,
            "limits": meta,
            "active": True,
            "mock": True,
        }
    if action == "remove":
        user = args[1]
        (root / f"{user}.json").unlink(missing_ok=True)
        return {"user": user, "removed": True, "mock": True}
    if action == "status-all":
        out = []
        for f in root.glob("*.json"):
            out.append(_mock(["status", f.stem]))
        return out  # type: ignore[return-value]
    if action == "status":
        user = args[1]
        path = root / f"{user}.json"
        limits = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return {
            "user": user,
            "slice": f"vz-pulse-{user}.slice",
            "memory_current_bytes": 0,
            "memory_max_bytes": int(limits.get("memory_mb") or 0) * 1024 * 1024,
            "tasks_current": 0,
            "cpu_usage_usec": 0,
            "disk_bytes": 0,
            "inodes_used": 0,
            "limits": limits,
            "active": path.exists(),
            "mock": True,
        }
    if action == "check":
        return {"ok": True, "mock": True}
    return {"mock": True}


def apply_pulse_for_user(user: User) -> dict[str, Any]:
    """Applique le slice Pulse selon le package / quota du compte."""
    if user.role == User.Role.ADMINISTRATOR:
        return {"skipped": True, "reason": "administrator"}
    jail = _jail_name(user)
    limits = _limits_from_user(user)
    args = [
        "apply",
        jail,
        "--cpu-millicores",
        str(limits["cpu_millicores"]),
        "--memory-mb",
        str(limits["memory_mb"]),
        "--tasks",
        str(limits["tasks"]),
        "--io-weight",
        str(limits["io_weight"]),
    ]
    try:
        data = _run(args)
    except VZoneAPIException as exc:
        logger.warning("Pulse apply failed for %s: %s", jail, exc.detail)
        return {"ok": False, "error": str(exc.detail), "limits": limits}
    data["ok"] = True
    data["inode_limit"] = limits["inode_limit"]
    return data


def remove_pulse_for_user(user: User) -> dict[str, Any]:
    jail = _jail_name(user)
    try:
        return _run(["remove", jail])
    except VZoneAPIException as exc:
        logger.warning("Pulse remove failed for %s: %s", jail, exc.detail)
        return {"ok": False, "error": str(exc.detail)}


def status_for_user(user: User) -> dict[str, Any]:
    jail = _jail_name(user)
    limits = _limits_from_user(user)
    try:
        data = _run(["status", jail])
    except VZoneAPIException:
        data = {
            "user": jail,
            "active": False,
            "memory_current_bytes": 0,
            "tasks_current": 0,
            "disk_bytes": 0,
            "inodes_used": 0,
            "limits": {},
        }
    # Enrichir avec quotas package
    mem_cur = int(data.get("memory_current_bytes") or 0)
    mem_max = int(data.get("memory_max_bytes") or 0) or (limits["memory_mb"] * 1024 * 1024)
    inodes_used = int(data.get("inodes_used") or 0)
    inode_limit = limits["inode_limit"]
    disk_bytes = int(data.get("disk_bytes") or 0)
    disk_limit = 0
    quota = getattr(user, "quota", None)
    if quota and not quota.unlimited_disk:
        disk_limit = int(quota.disk_mb) * 1024 * 1024

    def pct(used: int, limit: int) -> float | None:
        if not limit:
            return None
        return round(min(100.0, (used / limit) * 100.0), 1)

    return {
        "engine": "pulse",
        "brand": "V-zone Pulse",
        "username": jail,
        "active": bool(data.get("active")),
        "mock": bool(data.get("mock")) or provision_mode() == "mock",
        "provision_mode": provision_mode(),
        "slice": data.get("slice") or f"vz-pulse-{jail}.slice",
        "cpu": {
            "millicores_limit": limits["cpu_millicores"] or None,
            "usage_usec": int(data.get("cpu_usage_usec") or 0),
            "unlimited": limits["cpu_millicores"] == 0,
        },
        "memory": {
            "used_bytes": mem_cur,
            "limit_bytes": mem_max or None,
            "used_mb": round(mem_cur / (1024 * 1024), 1),
            "limit_mb": limits["memory_mb"] or None,
            "percent": pct(mem_cur, mem_max),
            "unlimited": limits["memory_mb"] == 0,
        },
        "tasks": {
            "current": int(data.get("tasks_current") or 0),
            "limit": limits["tasks"] or None,
            "percent": pct(int(data.get("tasks_current") or 0), limits["tasks"]),
        },
        "disk": {
            "used_bytes": disk_bytes,
            "limit_bytes": disk_limit or None,
            "used_mb": round(disk_bytes / (1024 * 1024), 1),
            "percent": pct(disk_bytes, disk_limit) if disk_limit else None,
        },
        "inodes": {
            "used": inodes_used,
            "limit": inode_limit or None,
            "percent": pct(inodes_used, inode_limit) if inode_limit else None,
        },
        "io_weight": limits["io_weight"],
        "limits_raw": data.get("limits") or limits,
    }


def status_all() -> list[dict[str, Any]]:
    try:
        raw = _run(["status-all"])
    except VZoneAPIException:
        return []
    if isinstance(raw, list):
        return raw
    return []


def overview() -> dict[str, Any]:
    rows = status_all()
    active = sum(1 for r in rows if r.get("active"))
    return {
        "engine": "pulse",
        "brand": "V-zone Pulse",
        "tagline": "Resource Governor — cgroups v2 / systemd, sans noyau propriétaire",
        "accounts_tracked": len(rows),
        "slices_active": active,
        "provision_mode": provision_mode(),
        "accounts": rows[:200],
    }
