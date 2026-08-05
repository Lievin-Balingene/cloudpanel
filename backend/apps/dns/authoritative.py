"""Publication DNS autoritaire : export zones BIND + demande de reload."""
from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from shutil import which

from django.conf import settings
from django.db import transaction

from apps.dns.models import DnsRecord, DnsZone

logger = logging.getLogger(__name__)

_SAFE_ZONE = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$", re.I)


def dns_zones_dir() -> Path:
    raw = getattr(settings, "VZONE_DNS_ZONES_DIR", None) or str(
        Path(getattr(settings, "VZONE_DATA_ROOT", "/var/lib/vzone")) / "named" / "zones"
    )
    return Path(raw)


def dns_reload_flag() -> Path:
    raw = getattr(settings, "VZONE_DNS_RELOAD_FLAG", None) or str(
        Path(getattr(settings, "VZONE_DATA_ROOT", "/var/lib/vzone")) / "named" / "reload.requested"
    )
    return Path(raw)


def dns_zones_conf() -> Path:
    raw = getattr(settings, "VZONE_DNS_ZONES_CONF", None) or str(
        Path(getattr(settings, "VZONE_DATA_ROOT", "/var/lib/vzone")) / "named" / "zones.conf"
    )
    return Path(raw)


def _normalize_soa_name(value: str, *, default: str) -> str:
    """BIND SOA MNAME/RNAME : FQDN avec point final, e-mail admin@x → admin.x."""
    raw = (value or "").strip()
    if not raw:
        raw = default
    if "@" in raw:
        local, _, domain = raw.partition("@")
        raw = f"{local}.{domain}" if domain else local
    raw = raw.rstrip(".")
    return f"{raw}." if raw else default


def _txt_rdata(content: str) -> str:
    """
    TXT BIND : chaînes max 255 octets. Les clés DKIM (RSA-2048) dépassent
    largement — sans découpage, named refuse la zone entière (SERVFAIL).
    """
    raw = (content or "").strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        raw = raw[1:-1]
    escaped = raw.replace("\\", "\\\\").replace('"', '\\"')
    if not escaped:
        return '""'
    chunks = [escaped[i : i + 255] for i in range(0, len(escaped), 255)]
    return " ".join(f'"{chunk}"' for chunk in chunks)


def _rdata(record: DnsRecord) -> str:
    rtype = record.record_type.upper()
    content = (record.content or "").strip()
    if rtype in {"NS", "CNAME", "MX", "SRV"} and content and not content.endswith("."):
        # Absolute target preferred; relative names get trailing dot as FQDN-ish
        if "." in content:
            content = f"{content}."
    if rtype == "TXT":
        return _txt_rdata(content)
    if rtype == "MX":
        prio = record.priority if record.priority is not None else 10
        return f"{prio} {content}"
    if rtype == "SRV":
        prio = record.priority if record.priority is not None else 0
        weight = record.weight if record.weight is not None else 0
        port = record.port if record.port is not None else 0
        return f"{prio} {weight} {port} {content}"
    if rtype == "CAA":
        flags = record.flags if record.flags is not None else 0
        tag = record.tag or "issue"
        val = content.strip('"')
        return f'{flags} {tag} "{val}"'
    return content


def render_zone_file(zone: DnsZone) -> str:
    """Génère un fichier de zone BIND (master)."""
    origin = zone.name.rstrip(".")
    primary_ns = _normalize_soa_name(zone.soa_primary_ns, default="ns1.vzone.local.")
    admin = _normalize_soa_name(zone.soa_admin_email, default="hostmaster.vzone.local.")
    lines: list[str] = [
        f"; V-zone authoritative zone for {origin}",
        f"$TTL {int(zone.ttl_default or 14400)}",
        f"$ORIGIN {origin}.",
        (
            f"@ IN SOA {primary_ns} {admin} ("
            f" {int(zone.soa_serial)} {int(zone.soa_refresh)} {int(zone.soa_retry)}"
            f" {int(zone.soa_expire)} {int(zone.soa_minimum)} )"
        ),
    ]
    for rec in zone.records.filter(is_active=True).order_by("record_type", "name", "id"):
        owner = "@" if rec.name in {"@", ""} else rec.name.rstrip(".")
        ttl = int(rec.ttl) if rec.ttl else int(zone.ttl_default or 14400)
        rdata = _rdata(rec)
        if not rdata:
            continue
        lines.append(f"{owner}\t{ttl}\tIN\t{rec.record_type.upper()}\t{rdata}")
    lines.append("")
    return "\n".join(lines)


def _zone_path(zone_name: str) -> Path:
    safe = zone_name.lower().rstrip(".")
    if not _SAFE_ZONE.match(safe) or ".." in safe:
        raise ValueError(f"Nom de zone invalide pour export: {zone_name}")
    return dns_zones_dir() / f"{safe}.zone"


def write_zone_file(zone: DnsZone) -> Path | None:
    if not zone.is_active:
        remove_zone_file(zone.name)
        return None
    path = _zone_path(zone.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = render_zone_file(zone)
    tmp = path.with_suffix(".zone.tmp")
    tmp.write_text(content, encoding="utf-8")
    if not _named_checkzone(zone.name, tmp):
        tmp.unlink(missing_ok=True)
        # Retirer l'ancienne version cassée pour éviter un SERVFAIL permanent.
        path.unlink(missing_ok=True)
        logger.error("Zone BIND invalide (non publiée): %s", zone.name)
        return None
    tmp.replace(path)
    try:
        os.chmod(path, 0o644)
    except OSError:
        pass
    return path


def _named_checkzone(zone_name: str, path: Path) -> bool:
    """Valide le fichier avec named-checkzone si disponible (évite SERVFAIL)."""
    helper = which("named-checkzone")
    if not helper:
        return True
    try:
        result = subprocess.run(
            [helper, zone_name.rstrip("."), str(path)],
            check=False,
            timeout=30,
            capture_output=True,
            text=True,
        )
    except Exception:  # noqa: BLE001
        logger.exception("named-checkzone failed for %s", zone_name)
        return True  # ne bloque pas si l'outil plante
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        logger.error("named-checkzone %s: %s", zone_name, detail[:2000])
        return False
    return True


def remove_zone_file(zone_name: str) -> None:
    try:
        path = _zone_path(zone_name)
    except ValueError:
        return
    if path.exists():
        path.unlink(missing_ok=True)


def write_zones_conf(zones: list[DnsZone] | None = None) -> Path:
    """Écrit zones.conf inclus par named (masters locaux)."""
    if zones is None:
        zones = list(DnsZone.objects.filter(is_active=True).order_by("name"))
    conf = dns_zones_conf()
    conf.parent.mkdir(parents=True, exist_ok=True)
    blocks: list[str] = [
        "// Auto-generated by V-zone — do not edit",
        "",
    ]
    for zone in zones:
        name = zone.name.rstrip(".")
        try:
            zpath = _zone_path(name)
        except ValueError:
            continue
        if not zpath.exists():
            continue
        blocks.append(
            "\n".join(
                [
                    f'zone "{name}" IN {{',
                    "    type master;",
                    f'    file "{zpath.as_posix()}";',
                    "    allow-query { any; };",
                    "    allow-transfer { none; };",
                    "};",
                    "",
                ]
            )
        )
    conf.write_text("\n".join(blocks), encoding="utf-8")
    try:
        os.chmod(conf, 0o644)
    except OSError:
        pass
    return conf


def request_named_reload() -> None:
    """Demande un rndc reload via flag systemd (comme nginx)."""
    helper = Path("/usr/local/sbin/vzone-named-reload")
    if helper.is_file() and os.access(helper, os.X_OK):
        try:
            subprocess.run([str(helper)], check=False, timeout=30, capture_output=True)
            return
        except Exception:  # noqa: BLE001
            logger.exception("vzone-named-reload failed")
    flag = dns_reload_flag()
    try:
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text("1\n", encoding="utf-8")
    except OSError:
        logger.exception("Impossible d'écrire le flag reload DNS %s", flag)
    try:
        subprocess.run(
            ["systemctl", "start", "vzone-named-reload.service"],
            check=False,
            timeout=15,
            capture_output=True,
        )
    except Exception:  # noqa: BLE001
        pass


def ensure_ns_glue_records(*, public_ip: str | None = None) -> int:
    """
    Ajoute des A (glue) pour ns1/ns2… dans la zone parent si hébergée localement.
    Ex. ns1.vzonecloud.co.uk → A dans zone vzonecloud.co.uk.
    """
    from apps.server_setup.services import default_nameservers

    ip = (public_ip or getattr(settings, "VZONE_PUBLIC_IP", "") or "").strip()
    if not ip:
        return 0
    ns_list = [n for n in default_nameservers() if n]
    created = 0
    for ns in ns_list:
        host = ns.rstrip(".").lower()
        parts = host.split(".")
        if len(parts) < 3:
            continue
        label = parts[0]
        parent = ".".join(parts[1:])
        zone = DnsZone.objects.filter(name=parent, is_active=True).first()
        if not zone:
            continue
        _, was_created = DnsRecord.objects.update_or_create(
            zone=zone,
            record_type="A",
            name=label,
            defaults={"content": ip, "ttl": zone.ttl_default, "is_active": True},
        )
        if was_created:
            created += 1
            zone.bump_serial()
    return created


def sync_zone_to_named(zone: DnsZone | None = None, *, zone_name: str | None = None) -> None:
    """Écrit une zone (ou la retire) puis régénère zones.conf + reload."""
    if zone is None and zone_name:
        zone = DnsZone.objects.filter(name=zone_name.rstrip(".")).first()
        if zone is None:
            remove_zone_file(zone_name)
            write_zones_conf()
            request_named_reload()
            return
    if zone is None:
        return
    write_zone_file(zone)
    write_zones_conf()
    request_named_reload()


def sync_all_zones_to_named(*, ensure_glue: bool = True) -> int:
    """Exporte toutes les zones actives vers BIND."""
    if ensure_glue:
        try:
            ensure_ns_glue_records()
        except Exception:  # noqa: BLE001
            logger.exception("Glue NS")
    try:
        from apps.domains.services import heal_all_subdomain_dns

        heal_all_subdomain_dns()
    except Exception:  # noqa: BLE001
        logger.exception("Heal subdomain DNS")
    zones = list(DnsZone.objects.filter(is_active=True).prefetch_related("records"))
    # Clean orphan zone files
    zdir = dns_zones_dir()
    zdir.mkdir(parents=True, exist_ok=True)
    expected = {f"{z.name.rstrip('.').lower()}.zone" for z in zones}
    for path in zdir.glob("*.zone"):
        if path.name not in expected:
            path.unlink(missing_ok=True)
    for zone in zones:
        write_zone_file(zone)
    write_zones_conf(zones)
    request_named_reload()
    return len(zones)


def schedule_zone_sync(zone: DnsZone | None = None, *, zone_name: str | None = None) -> None:
    """Sync after commit (évite fichiers partiels pendant une transaction)."""

    def _run() -> None:
        try:
            if zone is not None:
                # Re-fetch to get latest serial/records
                z = DnsZone.objects.filter(pk=zone.pk).prefetch_related("records").first()
                if z:
                    sync_zone_to_named(z)
                else:
                    sync_zone_to_named(zone_name=zone.name)
            elif zone_name:
                sync_zone_to_named(zone_name=zone_name)
            else:
                sync_all_zones_to_named()
        except Exception:  # noqa: BLE001
            logger.exception("Sync DNS named échoué")

    transaction.on_commit(_run)
