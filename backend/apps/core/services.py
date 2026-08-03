"""Services de santé et métriques système."""
from __future__ import annotations

import platform
import shutil
from dataclasses import asdict, dataclass
from typing import Any

import psutil
from django.conf import settings
from django.db import connection
from django.utils import timezone

from vzone import __version__


@dataclass(slots=True)
class HealthStatus:
    status: str
    version: str
    timestamp: str
    checks: dict[str, Any]


def check_database() -> dict[str, Any]:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001 — on expose l'état, pas le traceback
        return {"ok": False, "error": str(exc)}


def check_cache() -> dict[str, Any]:
    from django.core.cache import cache

    try:
        key = "vzone:health:ping"
        cache.set(key, "pong", 10)
        ok = cache.get(key) == "pong"
        return {"ok": ok}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def collect_system_metrics() -> dict[str, Any]:
    """Collecte CPU, RAM, disque, load average et température si disponible."""
    mem = psutil.virtual_memory()
    disk = shutil.disk_usage("/")
    cpu_percent = psutil.cpu_percent(interval=0.1)
    load: list[float] | None = None
    try:
        load = list(psutil.getloadavg())
    except (AttributeError, OSError):
        load = None

    temperatures: dict[str, float] = {}
    try:
        temps = psutil.sensors_temperatures()
        for name, entries in temps.items():
            if entries:
                temperatures[name] = float(entries[0].current)
    except (AttributeError, OSError):
        temperatures = {}

    return {
        "cpu": {
            "percent": cpu_percent,
            "count": psutil.cpu_count() or 0,
        },
        "memory": {
            "total": mem.total,
            "available": mem.available,
            "percent": mem.percent,
            "used": mem.used,
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": round((disk.used / disk.total) * 100, 2) if disk.total else 0,
        },
        "load_average": load,
        "temperatures": temperatures,
        "boot_time": psutil.boot_time(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "collected_at": timezone.now().isoformat(),
    }


def build_health_status() -> HealthStatus:
    checks = {
        "database": check_database(),
        "cache": check_cache(),
    }
    healthy = all(item.get("ok") for item in checks.values())
    return HealthStatus(
        status="healthy" if healthy else "degraded",
        version=getattr(settings, "VZONE_VERSION", __version__),
        timestamp=timezone.now().isoformat(),
        checks=checks,
    )


def health_as_dict() -> dict[str, Any]:
    return asdict(build_health_status())
