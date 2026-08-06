"""Collecte et agrégation des métriques dashboard."""
from __future__ import annotations

import logging
import os
import shutil
import stat as statmod
import subprocess
from datetime import timedelta
from pathlib import Path
from typing import Any

import psutil
from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from apps.accounts.models import User
from apps.core.services import collect_system_metrics
from apps.dashboard.models import ResourceSnapshot

logger = logging.getLogger(__name__)


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
