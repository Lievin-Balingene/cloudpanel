"""Collecte et agrégation des métriques dashboard."""
from __future__ import annotations

import shutil
from datetime import timedelta
from typing import Any

import psutil
from django.db.models import Count
from django.utils import timezone

from apps.accounts.models import User
from apps.core.services import collect_system_metrics
from apps.dashboard.models import ResourceSnapshot


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
            "net_bytes_sent": s.net_bytes_sent,
            "net_bytes_recv": s.net_bytes_recv,
        }
        for s in qs
    ]


def service_statuses() -> list[dict[str, Any]]:
    """Vérifie l'état de services critiques (best-effort, multi-OS)."""
    candidates = [
        ("postgresql", ["postgres", "postgresql"]),
        ("redis", ["redis-server", "redis"]),
        ("nginx", ["nginx"]),
        ("vzone-api", ["daphne", "vzone"]),
    ]
    running = {p.info["name"].lower() for p in psutil.process_iter(["name"]) if p.info.get("name")}
    results = []
    for label, names in candidates:
        ok = any(any(n in proc for n in names) for proc in running)
        results.append({"name": label, "active": ok})
    return results


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
    disk = shutil.disk_usage("/")
    return {
        "users_total": users.count(),
        "users_by_role": role_counts,
        "clients": role_counts.get("client", 0),
        "resellers": role_counts.get("reseller", 0),
        "dns_zones": zones.count(),
        "domains_total": domains.count(),
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
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": round(disk.used / disk.total * 100, 2) if disk.total else 0,
        },
        "services": service_statuses() if user.role == User.Role.ADMINISTRATOR else [],
        "metrics": collect_system_metrics() if user.role != User.Role.CLIENT else None,
    }
