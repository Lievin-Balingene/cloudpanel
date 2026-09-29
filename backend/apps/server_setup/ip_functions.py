"""Usage IP serveur + changement d'IP de site."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.conf import settings

from apps.core.exceptions import VZoneAPIException
from apps.server_setup.models import ServerSetup


def _public_ip() -> str:
    return (getattr(settings, "VZONE_PUBLIC_IP", "") or "").strip()


def list_server_ips() -> list[str]:
    setup = ServerSetup.get_solo()
    ips: list[str] = []
    pub = _public_ip()
    if pub:
        ips.append(pub)
    for raw in setup.extra_ips or []:
        ip = str(raw or "").strip()
        if ip and ip not in ips:
            ips.append(ip)
    return ips


def ip_usage_payload() -> dict[str, Any]:
    from apps.domains.models import Domain
    from apps.firewall.models import FirewallRule

    pub = _public_ip()
    server_ips = list_server_ips()

    by_ip: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"ip": "", "domains": [], "accounts": set()}
    )

    qs = Domain.objects.select_related("owner").filter(is_active=True)
    for d in qs:
        ip = (d.ipv4_address or pub or "").strip() or "(non assignée)"
        entry = by_ip[ip]
        entry["ip"] = ip
        entry["domains"].append(
            {
                "id": d.id,
                "name": d.name,
                "domain_type": d.domain_type,
                "owner": d.owner.username if d.owner_id else "",
                "owner_id": d.owner_id,
                "ipv4_address": d.ipv4_address,
            }
        )
        if d.owner_id:
            entry["accounts"].add(d.owner.username)

    # IPs serveur sans domaine
    for ip in server_ips:
        if ip not in by_ip:
            by_ip[ip] = {"ip": ip, "domains": [], "accounts": set()}

    usage = []
    for ip, data in sorted(by_ip.items(), key=lambda x: x[0]):
        usage.append(
            {
                "ip": data["ip"],
                "is_primary": data["ip"] == pub,
                "domain_count": len(data["domains"]),
                "account_count": len(data["accounts"]),
                "accounts": sorted(data["accounts"]),
                "domains": data["domains"],
            }
        )

    deny_rules = list(
        FirewallRule.objects.filter(action=FirewallRule.Action.DENY, is_enabled=True)
        .order_by("-priority", "id")
        .values(
            "id",
            "name",
            "source_cidr",
            "protocol",
            "port_start",
            "port_end",
            "is_applied",
            "notes",
        )
    )

    return {
        "public_ip": pub,
        "server_ips": server_ips,
        "extra_ips": list(ServerSetup.get_solo().extra_ips or []),
        "usage": usage,
        "deny_rules": deny_rules,
        "totals": {
            "ips": len(usage),
            "domains": qs.count(),
            "deny_rules": len(deny_rules),
        },
    }


def add_extra_ip(ip: str) -> dict[str, Any]:
    ip = (ip or "").strip()
    if not ip:
        raise VZoneAPIException(
            detail="Adresse IP requise.",
            code="invalid_ip",
            status_code=400,
        )
    setup = ServerSetup.get_solo()
    extras = list(setup.extra_ips or [])
    pub = _public_ip()
    if ip == pub or ip in extras:
        raise VZoneAPIException(
            detail="Cette IP est déjà enregistrée.",
            code="ip_exists",
            status_code=400,
        )
    extras.append(ip)
    setup.extra_ips = extras
    setup.save(update_fields=["extra_ips", "updated_at"])
    return ip_usage_payload()


def remove_extra_ip(ip: str) -> dict[str, Any]:
    ip = (ip or "").strip()
    setup = ServerSetup.get_solo()
    extras = [x for x in (setup.extra_ips or []) if str(x).strip() != ip]
    setup.extra_ips = extras
    setup.save(update_fields=["extra_ips", "updated_at"])
    return ip_usage_payload()


def change_domain_ip(*, domain_id: int, ipv4: str | None, actor) -> dict[str, Any]:
    from apps.domains.models import Domain
    from apps.domains.services import domains_queryset_for
    from apps.domains.vhosts import sync_domain_vhost

    domain = domains_queryset_for(actor).filter(pk=domain_id).first()
    if domain is None:
        raise VZoneAPIException(
            detail="Domaine introuvable.",
            code="not_found",
            status_code=404,
        )
    new_ip = (ipv4 or "").strip() or None
    if new_ip:
        allowed = set(list_server_ips())
        # Autoriser aussi l'IP actuelle et toute IP déjà utilisée
        if allowed and new_ip not in allowed and new_ip != (domain.ipv4_address or ""):
            # Accepter toute IPv4 valide même hors liste (ajout soft)
            pass
    domain.ipv4_address = new_ip
    domain.save(update_fields=["ipv4_address", "updated_at"])
    try:
        sync_domain_vhost(domain)
    except Exception:  # noqa: BLE001
        pass
    # Mettre à jour l'enregistrement A si zone liée
    try:
        from apps.domains.services import _ensure_a_record

        if domain.dns_zone_id and new_ip:
            _ensure_a_record(domain.dns_zone, "@", new_ip)
            _ensure_a_record(domain.dns_zone, "www", new_ip)
    except Exception:  # noqa: BLE001
        pass
    return {
        "id": domain.id,
        "name": domain.name,
        "ipv4_address": domain.ipv4_address,
        "owner": domain.owner.username if domain.owner_id else "",
    }
