"""Collecte et agrégation des métriques dashboard."""
from __future__ import annotations

import logging
import os
import re
import shutil
import socket
import stat as statmod
import subprocess
import time as time_module
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import psutil
from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from apps.accounts.models import User
from apps.core.exceptions import SystemOperationError, VZoneAPIException
from apps.core.services import collect_system_metrics
from apps.dashboard.models import ResourceSnapshot

logger = logging.getLogger(__name__)

NGINX_ACCESS_RE = re.compile(
    r'^(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<time>[^\]]+)\]\s+'
    r'"(?P<method>[A-Z]+)\s+(?P<path>\S+)(?:\s+HTTP/[^"]+)?"\s+'
    r"(?P<status>\d{3})\s+"
)


def capture_snapshot() -> ResourceSnapshot:
    metrics = collect_system_metrics()
    load = metrics.get("load_average") or [None, None, None]
    net = psutil.net_io_counters()
    return ResourceSnapshot.objects.create(
        collected_at=timezone.now(),
        cpu_percent=metrics["cpu"]["percent"],
        ram_percent=metrics["memory"]["percent"],
        ram_used=metrics["memory"]["used"],
        ram_total=metrics["memory"]["total"],
        disk_percent=metrics["disk"]["percent"],
        disk_used=metrics["disk"]["used"],
        disk_total=metrics["disk"]["total"],
        load_1=load[0] if load else None,
        load_5=load[1] if load and len(load) > 1 else None,
        load_15=load[2] if load and len(load) > 2 else None,
        net_bytes_sent=getattr(net, "bytes_sent", 0),
        net_bytes_recv=getattr(net, "bytes_recv", 0),
        temperatures=metrics.get("temperatures") or {},
        process_count=len(psutil.pids()),
    )


def prune_snapshots(retain_hours: int = 72) -> int:
    cutoff = timezone.now() - timedelta(hours=retain_hours)
    deleted, _ = ResourceSnapshot.objects.filter(collected_at__lt=cutoff).delete()
    return deleted


def history(hours: int = 24, limit: int = 288) -> list[dict[str, Any]]:
    since = timezone.now() - timedelta(hours=hours)
    qs = ResourceSnapshot.objects.filter(collected_at__gte=since).order_by("collected_at")[:limit]
    return [
        {
            "collected_at": s.collected_at.isoformat(),
            "cpu_percent": s.cpu_percent,
            "ram_percent": s.ram_percent,
            "disk_percent": s.disk_percent,
            "load_1": s.load_1,
            "load_5": s.load_5,
            "load_15": s.load_15,
            "ram_used": s.ram_used,
            "ram_total": s.ram_total,
            "disk_used": s.disk_used,
            "disk_total": s.disk_total,
            "net_bytes_sent": s.net_bytes_sent,
            "net_bytes_recv": s.net_bytes_recv,
            "process_count": s.process_count,
        }
        for s in qs
    ]


def _tail_lines(path: Path, max_bytes: int = 2 * 1024 * 1024) -> list[str]:
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - max_bytes))
        data = handle.read()
    if size > max_bytes:
        data = data.split(b"\n", 1)[-1]
    return data.decode("utf-8", errors="replace").splitlines()


def visitors_for(user: User, hours: int = 24) -> dict[str, Any]:
    """Agrège les dernières lignes des journaux Nginx des domaines accessibles."""
    from apps.domains.services import domains_queryset_for
    from apps.domains.vhosts import SAFE_NAME_RE

    hours = max(1, min(int(hours), 24 * 31))
    cutoff = timezone.now() - timedelta(hours=hours)
    paths: Counter[str] = Counter()
    ips: Counter[str] = Counter()
    recent_rows: list[tuple[datetime, dict[str, Any]]] = []
    error_rows: list[tuple[datetime, dict[str, Any]]] = []
    readable_logs = 0

    for domain_name in domains_queryset_for(user).values_list("name", flat=True).distinct():
        safe_domain = SAFE_NAME_RE.sub("_", domain_name.lower())
        for suffix in (".access.log", ".ssl.access.log"):
            log_path = Path("/var/log/nginx") / f"{safe_domain}{suffix}"
            try:
                lines = _tail_lines(log_path)
            except OSError:
                continue
            readable_logs += 1
            for line in lines:
                match = NGINX_ACCESS_RE.match(line)
                if not match:
                    continue
                try:
                    occurred_at = datetime.strptime(
                        match.group("time"),
                        "%d/%b/%Y:%H:%M:%S %z",
                    )
                except ValueError:
                    continue
                if occurred_at < cutoff:
                    continue
                target = match.group("path")
                clean_path = target.split("?", 1)[0]
                ip = match.group("ip")
                status_code = int(match.group("status"))
                row = {
                    "ip": ip,
                    "method": match.group("method"),
                    "path": target,
                    "status": status_code,
                    "time": occurred_at.isoformat(),
                }
                paths[clean_path] += 1
                ips[ip] += 1
                recent_rows.append((occurred_at, row))
                if status_code >= 400:
                    error_rows.append((occurred_at, row))

    recent_rows.sort(key=lambda item: item[0], reverse=True)
    error_rows.sort(key=lambda item: item[0], reverse=True)
    result: dict[str, Any] = {
        "visits": sum(ips.values()),
        "unique_ips": len(ips),
        "top_paths": [{"path": path, "hits": hits} for path, hits in paths.most_common(10)],
        "top_ips": [{"ip": ip, "hits": hits} for ip, hits in ips.most_common(10)],
        "recent": [row for _, row in recent_rows[:50]],
        "errors_sample": [row for _, row in error_rows[:20]],
    }
    if readable_logs == 0:
        result["note"] = "Aucun journal Nginx lisible pour les domaines de ce compte."
    return result


_SERVICE_CANDIDATES: list[tuple[str, list[str], list[str]]] = [
    # label, systemd units, process name fragments
    ("nginx", ["nginx"], ["nginx"]),
    ("postgresql", ["postgresql", "pgsql"], ["postgres", "postgresql"]),
    ("mysql", ["mariadb", "mysql", "mysqld"], ["mysqld", "mariadbd"]),
    ("redis", ["redis", "redis-server"], ["redis-server", "redis"]),
    ("postfix", ["postfix"], ["master", "postfix"]),
    ("dovecot", ["dovecot"], ["dovecot"]),
    ("opendkim", ["opendkim"], ["opendkim"]),
    ("fail2ban", ["fail2ban"], ["fail2ban-server", "fail2ban"]),
    ("sshd", ["sshd", "ssh"], ["sshd", "ssh"]),
    ("docker", ["docker"], ["dockerd"]),
    ("named", ["named", "bind9"], ["named", "bind"]),
    ("pure-ftpd", ["pure-ftpd", "vsftpd", "proftpd"], ["pure-ftpd", "vsftpd", "proftpd"]),
    ("vzone-api", ["vzone-api"], ["daphne", "gunicorn", "uvicorn"]),
    ("vzone-celery", ["vzone-celery", "vzone-worker"], ["celery"]),
    ("vzone-worker", ["vzone-beat", "vzone-celerybeat"], ["celery"]),
]

SVCCTL = Path("/usr/local/sbin/vzone-svcctl")
ALLOWED_SERVICE_ACTIONS = frozenset({"start", "stop", "restart", "reload"})


def _systemd_is_active(unit: str) -> bool | None:
    """True/False si systemctl répond, None si indisponible."""
    if "*" in unit:
        return None
    name = unit if unit.endswith(".service") else f"{unit}.service"
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    out = (proc.stdout or "").strip().lower()
    if out == "active":
        return True
    if out in {"inactive", "failed", "deactivating", "activating", "dead"}:
        return False
    # unit inconnue
    err = (proc.stderr or "").lower()
    if proc.returncode != 0 and ("could not be found" in err or "not-found" in err):
        return None
    # is-active renvoie inactive avec code 3 souvent
    if out == "unknown" or "not-found" in out:
        return None
    return False if proc.returncode != 0 else True


def _resolve_unit(label: str, units: list[str]) -> tuple[str | None, bool | None]:
    """Retourne (unit_name, active) pour le premier unit systemd connu."""
    for unit in units:
        st = _systemd_is_active(unit)
        if st is not None:
            return unit, st
    return None, None


def service_statuses() -> list[dict[str, Any]]:
    """Vérifie l'état de services critiques (systemd puis fallback processus)."""
    running = {
        (p.info.get("name") or "").lower()
        for p in psutil.process_iter(["name"])
        if p.info.get("name")
    }
    cmdline_blob = " ".join(running)
    try:
        for p in psutil.process_iter(["cmdline"]):
            cmd = p.info.get("cmdline") or []
            if cmd:
                cmdline_blob += " " + " ".join(c.lower() for c in cmd if c)
    except (psutil.Error, OSError):
        pass

    helper_ok = SVCCTL.is_file()
    results: list[dict[str, Any]] = []
    for label, units, names in _SERVICE_CANDIDATES:
        unit, active = _resolve_unit(label, units)
        source = "systemd" if unit is not None else "process"
        if active is None:
            active = any(n in proc for proc in running for n in names) or any(
                n in cmdline_blob for n in names
            )
            if label == "postfix" and active:
                active = "postfix" in cmdline_blob
            source = "process"
            unit = units[0] if units else None
        results.append(
            {
                "name": label,
                "active": bool(active),
                "source": source,
                "unit": unit,
                "manageable": bool(helper_ok and unit),
            }
        )
    return results


def control_service(name: str, action: str) -> dict[str, Any]:
    """start|stop|restart|reload d'un service allowlisté via vzone-svcctl."""
    action = (action or "").strip().lower()
    name = (name or "").strip().lower()
    if action not in ALLOWED_SERVICE_ACTIONS:
        raise VZoneAPIException(
            detail="Action invalide (start, stop, restart, reload).",
            code="invalid_action",
            status_code=400,
        )

    unit: str | None = None
    for label, units, _names in _SERVICE_CANDIDATES:
        if label == name:
            resolved, _ = _resolve_unit(label, units)
            unit = resolved or (units[0] if units else None)
            break
    if not unit:
        raise VZoneAPIException(
            detail=f"Service inconnu: {name}",
            code="unknown_service",
            status_code=404,
        )

    if not SVCCTL.is_file():
        raise SystemOperationError(
            detail=(
                "Helper vzone-svcctl absent. "
                "Exécutez: sudo bash /opt/vzone-src/scripts/ensure-panel-helpers.sh"
            )
        )

    cmd = ["sudo", "-n", str(SVCCTL), action, unit]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SystemOperationError(detail=f"Timeout {action} {name}") from exc
    except OSError as exc:
        raise SystemOperationError(detail=str(exc)) from exc

    out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        logger.warning("svcctl %s %s failed: %s", action, unit, out)
        raise SystemOperationError(
            detail=out or f"Échec {action} sur {name} (code {proc.returncode})",
        )

    # Laisser systemd stabiliser puis relire l'état
    time_module.sleep(0.4)
    statuses = {s["name"]: s for s in service_statuses()}
    current = statuses.get(name) or {"name": name, "active": None, "unit": unit}
    return {
        "name": name,
        "action": action,
        "unit": unit,
        "active": current.get("active"),
        "output": out[:500],
        "service": current,
    }


def _bytes_rate(prev: int, curr: int, seconds: float) -> float:
    if seconds <= 0 or curr < prev:
        return 0.0
    return (curr - prev) / seconds


def _process_rows(
    limit: int = 20,
    primed: list[psutil.Process] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    procs = primed
    if procs is None:
        procs = []
        for proc in psutil.process_iter(["pid"]):
            try:
                proc.cpu_percent(interval=None)
                procs.append(proc)
            except (psutil.Error, OSError):
                continue
        time_module.sleep(0.12)
    rows: list[dict[str, Any]] = []
    attrs = ["pid", "name", "username", "memory_percent", "status", "create_time"]
    for proc in procs:
        try:
            info = proc.as_dict(attrs=attrs)
            rows.append(
                {
                    "pid": info.get("pid"),
                    "name": info.get("name") or "?",
                    "user": info.get("username") or "—",
                    "cpu_percent": float(proc.cpu_percent(interval=None) or 0),
                    "memory_percent": float(info.get("memory_percent") or 0),
                    "status": info.get("status") or "—",
                    "create_time": info.get("create_time") or 0,
                }
            )
        except (psutil.Error, OSError):
            continue
    by_cpu = sorted(rows, key=lambda r: r["cpu_percent"], reverse=True)[:limit]
    by_mem = sorted(rows, key=lambda r: r["memory_percent"], reverse=True)[:limit]
    return by_cpu, by_mem


def full_server_status() -> dict[str, Any]:
    """Snapshot live ultra-complet pour le monitoring WHM."""
    # Première lecture CPU pour amorcer les compteurs (delta) + amorçage processus
    psutil.cpu_percent(interval=None)
    per_cpu_prime = psutil.cpu_percent(interval=None, percpu=True)
    primed_procs: list[psutil.Process] = []
    for proc in psutil.process_iter(["pid"]):
        try:
            proc.cpu_percent(interval=None)
            primed_procs.append(proc)
        except (psutil.Error, OSError):
            continue
    time_module.sleep(0.15)
    cpu_percent = float(psutil.cpu_percent(interval=None))
    per_cpu = psutil.cpu_percent(interval=None, percpu=True) or per_cpu_prime

    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    load: list[float] | None = None
    try:
        load = [float(x) for x in psutil.getloadavg()]
    except (AttributeError, OSError):
        load = None

    boot = float(psutil.boot_time())
    now_ts = timezone.now().timestamp()
    uptime_seconds = max(0, int(now_ts - boot))

    freq = None
    try:
        f = psutil.cpu_freq()
        if f:
            freq = {
                "current": round(float(f.current or 0), 1),
                "min": round(float(f.min or 0), 1) if f.min else None,
                "max": round(float(f.max or 0), 1) if f.max else None,
            }
    except (AttributeError, OSError, NotImplementedError):
        freq = None

    disks: list[dict[str, Any]] = []
    seen_mounts: set[str] = set()
    for part in psutil.disk_partitions(all=False):
        mount = part.mountpoint
        if not mount or mount in seen_mounts:
            continue
        # Ignore pseudo-FS courants
        if part.fstype.lower() in {"tmpfs", "devtmpfs", "squashfs", "overlay", "proc", "sysfs", "cgroup", "cgroup2"}:
            continue
        if mount.startswith(("/snap", "/run", "/sys", "/proc", "/dev")):
            continue
        try:
            usage = psutil.disk_usage(mount)
        except (PermissionError, OSError):
            continue
        seen_mounts.add(mount)
        disks.append(
            {
                "device": part.device,
                "mountpoint": mount,
                "fstype": part.fstype,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": float(usage.percent),
            }
        )
    disks.sort(key=lambda d: (0 if d["mountpoint"] == "/" else 1, d["mountpoint"]))

    disk_io = None
    try:
        io = psutil.disk_io_counters()
        if io:
            disk_io = {
                "read_bytes": int(io.read_bytes),
                "write_bytes": int(io.write_bytes),
                "read_count": int(io.read_count),
                "write_count": int(io.write_count),
                "read_time_ms": int(getattr(io, "read_time", 0) or 0),
                "write_time_ms": int(getattr(io, "write_time", 0) or 0),
            }
    except (AttributeError, OSError):
        disk_io = None

    net_total = psutil.net_io_counters()
    interfaces: list[dict[str, Any]] = []
    try:
        per_nic = psutil.net_io_counters(pernic=True) or {}
        addrs = psutil.net_if_addrs()
        stats_map = {}
        try:
            stats_map = psutil.net_if_stats()
        except (AttributeError, OSError):
            stats_map = {}
        for name, counters in sorted(per_nic.items()):
            if name.startswith(("lo", "docker", "br-", "veth", "virbr", "tun", "tap")):
                # garder loopback, ignorer bridges docker bruyants sauf s'ils ont du trafic
                if name != "lo" and counters.bytes_sent + counters.bytes_recv < 1024:
                    continue
            ip_v4 = ""
            for addr in addrs.get(name, []):
                if addr.family == socket.AF_INET:
                    ip_v4 = addr.address
                    break
            st = stats_map.get(name)
            interfaces.append(
                {
                    "name": name,
                    "ip": ip_v4,
                    "is_up": bool(getattr(st, "isup", True)),
                    "speed_mbps": int(getattr(st, "speed", 0) or 0),
                    "bytes_sent": int(counters.bytes_sent),
                    "bytes_recv": int(counters.bytes_recv),
                    "packets_sent": int(counters.packets_sent),
                    "packets_recv": int(counters.packets_recv),
                    "errin": int(counters.errin),
                    "errout": int(counters.errout),
                    "dropin": int(counters.dropin),
                    "dropout": int(counters.dropout),
                }
            )
    except (AttributeError, OSError):
        interfaces = []

    conn_summary = {"total": 0, "established": 0, "listen": 0, "time_wait": 0, "close_wait": 0, "other": 0}
    try:
        for c in psutil.net_connections(kind="inet"):
            conn_summary["total"] += 1
            status = (c.status or "").upper()
            if status == "ESTABLISHED":
                conn_summary["established"] += 1
            elif status == "LISTEN":
                conn_summary["listen"] += 1
            elif status == "TIME_WAIT":
                conn_summary["time_wait"] += 1
            elif status == "CLOSE_WAIT":
                conn_summary["close_wait"] += 1
            else:
                conn_summary["other"] += 1
    except (psutil.Error, OSError, PermissionError):
        pass

    # Débit réseau estimé via 2 derniers snapshots
    net_rates = {"sent_bps": 0.0, "recv_bps": 0.0}
    recent = list(ResourceSnapshot.objects.order_by("-collected_at")[:2])
    if len(recent) == 2:
        newer, older = recent[0], recent[1]
        dt = (newer.collected_at - older.collected_at).total_seconds()
        net_rates = {
            "sent_bps": _bytes_rate(older.net_bytes_sent, newer.net_bytes_sent, dt),
            "recv_bps": _bytes_rate(older.net_bytes_recv, newer.net_bytes_recv, dt),
        }

    temperatures: list[dict[str, Any]] = []
    try:
        temps = psutil.sensors_temperatures() or {}
        for chip, entries in temps.items():
            for entry in entries:
                temperatures.append(
                    {
                        "chip": chip,
                        "label": entry.label or chip,
                        "current": float(entry.current),
                        "high": float(entry.high) if entry.high else None,
                        "critical": float(entry.critical) if entry.critical else None,
                    }
                )
    except (AttributeError, OSError):
        temperatures = []

    fans: list[dict[str, Any]] = []
    try:
        fan_map = psutil.sensors_fans() or {}
        for chip, entries in fan_map.items():
            for entry in entries:
                fans.append(
                    {
                        "chip": chip,
                        "label": entry.label or chip,
                        "rpm": float(entry.current),
                    }
                )
    except (AttributeError, OSError):
        fans = []

    logged_users: list[dict[str, Any]] = []
    try:
        for u in psutil.users():
            logged_users.append(
                {
                    "name": u.name,
                    "terminal": u.terminal or "—",
                    "host": u.host or "local",
                    "started": float(u.started) if u.started else None,
                }
            )
    except (AttributeError, OSError):
        logged_users = []

    top_cpu, top_mem = _process_rows(18, primed=primed_procs)
    services = service_statuses()
    down = [s["name"] for s in services if not s["active"]]

    alerts = {"open": 0, "critical": 0, "warning": 0}
    try:
        from apps.monitoring.models import AlertEvent

        open_qs = AlertEvent.objects.filter(status=AlertEvent.Status.OPEN).select_related("rule")
        alerts["open"] = open_qs.count()
        for ev in open_qs[:50]:
            sev = getattr(ev.rule, "severity", "") or ""
            if sev == "critical":
                alerts["critical"] += 1
            elif sev == "warning":
                alerts["warning"] += 1
    except Exception:  # noqa: BLE001
        pass

    identity = _whm_statistics()
    health = "healthy"
    root_disk = next((d for d in disks if d["mountpoint"] == "/"), None)
    disk_pct = float(root_disk["percent"]) if root_disk else float(mem.percent)
    if down or alerts["critical"] > 0 or cpu_percent >= 95 or mem.percent >= 95 or disk_pct >= 95:
        health = "critical"
    elif alerts["open"] > 0 or cpu_percent >= 80 or mem.percent >= 80 or disk_pct >= 85 or (load and load[0] > (psutil.cpu_count() or 1) * 1.5):
        health = "degraded"

    return {
        "health": health,
        "collected_at": timezone.now().isoformat(),
        "identity": {
            **identity,
            "uptime_seconds": uptime_seconds,
            "boot_time": boot,
            "process_count": len(psutil.pids()),
            "cpu_count_logical": psutil.cpu_count(logical=True) or 0,
            "cpu_count_physical": psutil.cpu_count(logical=False) or 0,
        },
        "cpu": {
            "percent": cpu_percent,
            "per_cpu": [float(x) for x in (per_cpu or [])],
            "freq": freq,
            "load": {
                "1": load[0] if load else None,
                "5": load[1] if load and len(load) > 1 else None,
                "15": load[2] if load and len(load) > 2 else None,
            },
        },
        "memory": {
            "total": mem.total,
            "available": mem.available,
            "used": mem.used,
            "free": mem.free,
            "percent": float(mem.percent),
            "cached": int(getattr(mem, "cached", 0) or 0),
            "buffers": int(getattr(mem, "buffers", 0) or 0),
            "shared": int(getattr(mem, "shared", 0) or 0),
        },
        "swap": {
            "total": swap.total,
            "used": swap.used,
            "free": swap.free,
            "percent": float(swap.percent),
        },
        "disks": disks,
        "disk_io": disk_io,
        "network": {
            "bytes_sent": int(getattr(net_total, "bytes_sent", 0) or 0),
            "bytes_recv": int(getattr(net_total, "bytes_recv", 0) or 0),
            "rates": net_rates,
            "interfaces": interfaces,
            "connections": conn_summary,
        },
        "processes": {"top_cpu": top_cpu, "top_memory": top_mem},
        "services": services,
        "services_down": down,
        "temperatures": temperatures,
        "fans": fans,
        "users": logged_users,
        "alerts": alerts,
    }


def directory_size_bytes(path: Path) -> int:
    """Taille du répertoire en octets (home compte uniquement, sans suivre les symlinks)."""
    try:
        path = path.resolve(strict=False)
    except OSError:
        return 0
    if not path.is_dir():
        return 0

    # Linux : du -sb (ne suit pas les symlinks) — plus fiable qu'un walk Python
    try:
        proc = subprocess.run(
            ["du", "-sb", "--", str(path)],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return max(0, int(proc.stdout.split()[0]))
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("du fallback pour %s: %s", path, exc)

    total = 0
    try:
        root_dev = path.stat().st_dev
    except OSError:
        return 0
    try:
        for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
            # Ne pas descendre dans un autre montage / FS
            try:
                if Path(dirpath).stat().st_dev != root_dev:
                    dirnames[:] = []
                    continue
            except OSError:
                dirnames[:] = []
                continue
            # Ignorer les symlinks de répertoires
            alive = []
            for d in dirnames:
                dp = Path(dirpath) / d
                try:
                    if dp.is_symlink():
                        continue
                    if dp.stat().st_dev != root_dev:
                        continue
                    alive.append(d)
                except OSError:
                    continue
            dirnames[:] = alive
            for name in filenames:
                fp = Path(dirpath) / name
                try:
                    st = fp.lstat()
                    if statmod.S_ISLNK(st.st_mode) or not statmod.S_ISREG(st.st_mode):
                        continue
                    total += st.st_size
                except OSError:
                    continue
    except OSError as exc:
        logger.debug("directory_size_bytes %s: %s", path, exc)
    return total


def _account_home_for_disk(user: User) -> Path | None:
    """Home strictement sous VZONE_HOME_ROOT/<username> (jamais le root ni /)."""
    from apps.files.services import personal_home

    root = Path(settings.VZONE_HOME_ROOT).resolve()
    home_name = (user.system_username or user.username or "").strip().lower()
    if not home_name or home_name in {".", "..", "root", "home"} or "/" in home_name or "\\" in home_name:
        logger.warning("Disk usage: username invalide pour %s", user.pk)
        return None

    home = (root / home_name).resolve()
    # Doit être un enfant direct de HOME_ROOT
    try:
        if home.parent != root:
            logger.warning("Disk usage: home hors jail %s (root=%s)", home, root)
            return None
    except Exception:  # noqa: BLE001
        return None
    if home == root or home == Path("/"):
        return None

    # Préférer personal_home si cohérent
    try:
        ph = personal_home(user).resolve()
        if ph.parent == root and ph.name == home_name:
            home = ph
    except OSError:
        pass

    if not home.is_dir():
        return home  # taille 0
    return home


def account_disk_breakdown(home: Path) -> dict[str, int]:
    """Répartition par dossier de premier niveau (Mo utiles pour le debug UI)."""
    out: dict[str, int] = {}
    try:
        for child in home.iterdir():
            if child.is_symlink():
                continue
            if child.is_dir():
                out[child.name] = directory_size_bytes(child)
            elif child.is_file():
                try:
                    out[child.name] = child.stat().st_size
                except OSError:
                    out[child.name] = 0
    except OSError:
        pass
    return out


def account_disk_usage(user: User) -> dict[str, Any]:
    """Disk Usage limité au home du compte (style cPanel) — jamais le disque serveur."""
    from apps.packages.models import PackageAssignment

    home = _account_home_for_disk(user)
    used = directory_size_bytes(home) if home and home.is_dir() else 0
    breakdown = account_disk_breakdown(home) if home and home.is_dir() else {}

    assignment = PackageAssignment.objects.filter(user=user).select_related("package").first()
    pkg = assignment.package if assignment else None
    unlimited = bool(pkg and pkg.unlimited_disk)
    quota = getattr(user, "quota", None)

    if pkg and not unlimited and pkg.disk_mb > 0:
        total = int(pkg.disk_mb) * 1024 * 1024
        quota_mb = int(pkg.disk_mb)
    elif quota and not getattr(quota, "unlimited_disk", False) and (quota.disk_mb or 0) > 0:
        total = int(quota.disk_mb) * 1024 * 1024
        quota_mb = int(quota.disk_mb)
        unlimited = False
    else:
        total = used if used > 0 else 1
        quota_mb = None
        unlimited = True

    free = max(0, total - used) if not unlimited else 0
    percent = round(min(100.0, used / total * 100), 2) if total and not unlimited else 0.0
    used_mb = round(used / (1024 * 1024), 2)

    return {
        "total": total if not unlimited else used,
        "used": used,
        "free": free,
        "percent": percent,
        "used_mb": used_mb,
        "quota_mb": None if unlimited else quota_mb,
        "unlimited": unlimited,
        "home_directory": str(home) if home else "",
        "breakdown_mb": {
            k: round(v / (1024 * 1024), 2) for k, v in sorted(breakdown.items(), key=lambda x: -x[1])[:12]
        },
    }


def account_resource_counts(user: User) -> dict[str, int]:
    """Compteurs d'usage propres au compte."""
    from apps.domains.models import Domain

    counts: dict[str, int] = {
        # Domaines « package » : principal + addon (pas les sous-domaines)
        "domains": Domain.objects.filter(
            owner=user,
            domain_type__in={Domain.DomainType.PRIMARY, Domain.DomainType.ADDON},
        ).count(),
        "dns_zones": 0,
        "emails": 0,
        "databases": 0,
        "ftp_accounts": 0,
    }
    try:
        from apps.dns.models import DnsZone

        counts["dns_zones"] = DnsZone.objects.filter(owner=user).count()
    except Exception:  # noqa: BLE001
        pass
    try:
        from apps.email.models import Mailbox

        counts["emails"] = Mailbox.objects.filter(mail_domain__owner=user).count()
    except Exception:  # noqa: BLE001
        pass
    try:
        from apps.databases.models import Database

        counts["databases"] = Database.objects.filter(owner=user).count()
    except Exception:  # noqa: BLE001
        pass
    try:
        from apps.ftp.models import FtpAccount

        counts["ftp_accounts"] = FtpAccount.objects.filter(owner=user).count()
    except Exception:  # noqa: BLE001
        pass
    return counts


def account_info(user: User) -> dict[str, Any]:
    from apps.domains.models import Domain
    from apps.files.services import personal_home

    primary = (
        Domain.objects.filter(owner=user, domain_type=Domain.DomainType.PRIMARY, is_active=True)
        .order_by("created_at")
        .first()
    )
    home = personal_home(user)
    return {
        "username": user.username,
        "email": user.email,
        "home_directory": str(home),
        "primary_domain": primary.name if primary else "",
        "last_login_ip": user.last_login_ip or "",
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


def overview_for(user: User) -> dict[str, Any]:
    from apps.dns.models import DnsZone
    from apps.domains.models import Domain
    from apps.packages.models import HostingPackage, PackageAssignment

    if user.role == User.Role.ADMINISTRATOR:
        users = User.objects.all()
        zones = DnsZone.objects.all()
        packages = HostingPackage.objects.filter(is_active=True)
        domains = Domain.objects.all()
    elif user.role == User.Role.RESELLER:
        users = User.objects.filter(parent=user)
        zones = (
            DnsZone.objects.filter(owner__parent=user) | DnsZone.objects.filter(owner=user)
        ).distinct()
        packages = (
            HostingPackage.objects.filter(owner=user)
            | HostingPackage.objects.filter(owner__isnull=True, package_type="client")
        ).distinct()
        domains = Domain.objects.filter(owner__parent=user) | Domain.objects.filter(owner=user)
        domains = domains.distinct()
    else:
        users = User.objects.filter(pk=user.pk)
        zones = DnsZone.objects.filter(owner=user)
        packages = HostingPackage.objects.none()
        domains = Domain.objects.filter(owner=user)

    role_counts = dict(
        users.values("role").annotate(c=Count("id")).values_list("role", "c")
    )
    assignment = PackageAssignment.objects.filter(user=user).select_related("package").first()

    # Compte client : disk + infos limités au home / ressources du compte
    if user.role == User.Role.CLIENT:
        disk = account_disk_usage(user)
        usage = account_resource_counts(user)
        account = account_info(user)
        dns_zones_count = usage.get("dns_zones", 0)
        domains_total = usage.get("domains", 0)
    else:
        disk_raw = shutil.disk_usage("/")
        disk = {
            "total": disk_raw.total,
            "used": disk_raw.used,
            "free": disk_raw.free,
            "percent": round(disk_raw.used / disk_raw.total * 100, 2) if disk_raw.total else 0,
            "unlimited": False,
            "home_directory": "",
            "quota_mb": None,
        }
        usage = None
        account = None
        dns_zones_count = zones.count()
        domains_total = domains.count()

    return {
        "users_total": users.count(),
        "users_by_role": role_counts,
        "clients": role_counts.get("client", 0),
        "resellers": role_counts.get("reseller", 0),
        "dns_zones": dns_zones_count,
        "domains_total": domains_total,
        "packages_active": packages.count(),
        "sessions_active": User.objects.filter(
            sessions__is_revoked=False,
            sessions__expires_at__gt=timezone.now(),
        )
        .distinct()
        .count()
        if user.role == User.Role.ADMINISTRATOR
        else 0,
        "my_package": assignment.package.name if assignment else None,
        "disk": disk,
        "usage": usage,
        "account": account,
        "services": service_statuses() if user.role == User.Role.ADMINISTRATOR else [],
        "metrics": collect_system_metrics() if user.role != User.Role.CLIENT else None,
        "statistics": _whm_statistics() if user.role != User.Role.CLIENT else None,
    }


def _whm_statistics() -> dict[str, Any]:
    """Bloc Statistics style WHM (hostname, OS, load, produit)."""
    import platform
    import socket

    from vzone import get_version

    hostname = ""
    try:
        from apps.server_setup.services import get_setup_payload

        payload = get_setup_payload()
        hostname = (payload.get("hostname") or payload.get("os_hostname") or "").strip()
    except Exception:  # noqa: BLE001
        hostname = ""
    if not hostname:
        try:
            hostname = socket.getfqdn() or socket.gethostname()
        except OSError:
            hostname = platform.node() or "—"

    os_name = platform.system()
    os_release = platform.release()
    os_pretty = ""
    try:
        os_release_path = Path("/etc/os-release")
        if os_release_path.is_file():
            data = {}
            for line in os_release_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    data[k] = v.strip().strip('"')
            os_pretty = data.get("PRETTY_NAME") or data.get("NAME") or ""
    except OSError:
        os_pretty = ""
    if not os_pretty:
        os_pretty = f"{os_name} {os_release}".strip()

    return {
        "hostname": hostname,
        "operating_system": os_pretty,
        "product": f"V-zone Admin v{get_version()}",
        "version": get_version(),
        "platform": platform.machine() or "",
    }
