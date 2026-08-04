"""Services DNS : création de zone avec enregistrements SOA/NS par défaut."""
from __future__ import annotations

from django.db import transaction

from apps.accounts.models import User
from apps.dns.models import DnsRecord, DnsZone, normalize_zone_name


def _configured_nameservers() -> tuple[str, str, list[str]]:
    """Nameservers WHM (ServerSetup) avec repli historique."""
    try:
        from apps.server_setup.services import default_nameservers

        ns1, ns2, ns3, ns4 = default_nameservers()
        extras = [n for n in (ns3, ns4) if n]
        if ns1 and ns2:
            return ns1, ns2, extras
    except Exception:  # noqa: BLE001
        pass
    return "ns1.vzone.local.", "ns2.vzone.local.", []


@transaction.atomic
def create_zone_with_defaults(
    *,
    name: str,
    owner: User,
    primary_ns: str | None = None,
    secondary_ns: str | None = None,
    admin_email: str | None = None,
) -> DnsZone:
    cfg_ns1, cfg_ns2, extras = _configured_nameservers()
    primary_ns = primary_ns or cfg_ns1
    secondary_ns = secondary_ns or cfg_ns2
    if not admin_email:
        host = (primary_ns or "vzone.local.").rstrip(".")
        parts = host.split(".")
        domain = ".".join(parts[1:]) if len(parts) > 2 else host
        admin_email = f"hostmaster.{domain}."
    zone_name = normalize_zone_name(name)
    zone = DnsZone.objects.create(
        name=zone_name,
        owner=owner,
        soa_primary_ns=primary_ns if primary_ns.endswith(".") else f"{primary_ns}.",
        soa_admin_email=admin_email if admin_email.endswith(".") else f"{admin_email}.",
    )
    records = [
        DnsRecord(
            zone=zone,
            record_type="NS",
            name="@",
            content=primary_ns if primary_ns.endswith(".") else f"{primary_ns}.",
            ttl=86400,
        ),
        DnsRecord(
            zone=zone,
            record_type="NS",
            name="@",
            content=secondary_ns if secondary_ns.endswith(".") else f"{secondary_ns}.",
            ttl=86400,
        ),
    ]
    for extra in extras:
        content = extra if extra.endswith(".") else f"{extra}."
        records.append(
            DnsRecord(zone=zone, record_type="NS", name="@", content=content, ttl=86400)
        )
    DnsRecord.objects.bulk_create(records)
    try:
        from apps.dns.authoritative import schedule_zone_sync

        schedule_zone_sync(zone)
    except Exception:  # noqa: BLE001
        pass
    return zone


def zones_queryset_for(user: User):
    qs = DnsZone.objects.select_related("owner").prefetch_related("records")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return (qs.filter(owner__parent=user) | qs.filter(owner=user)).distinct()
    return qs.filter(owner=user)
