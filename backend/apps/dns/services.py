"""Services DNS : création de zone avec enregistrements SOA/NS par défaut."""
from __future__ import annotations

from django.db import transaction

from apps.accounts.models import User
from apps.dns.models import DnsRecord, DnsZone, normalize_zone_name


@transaction.atomic
def create_zone_with_defaults(
    *,
    name: str,
    owner: User,
    primary_ns: str = "ns1.vzone.local.",
    secondary_ns: str = "ns2.vzone.local.",
    admin_email: str = "hostmaster.vzone.local.",
) -> DnsZone:
    zone_name = normalize_zone_name(name)
    zone = DnsZone.objects.create(
        name=zone_name,
        owner=owner,
        soa_primary_ns=primary_ns if primary_ns.endswith(".") else f"{primary_ns}.",
        soa_admin_email=admin_email if admin_email.endswith(".") else f"{admin_email}.",
    )
    DnsRecord.objects.bulk_create(
        [
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
    )
    return zone


def zones_queryset_for(user: User):
    qs = DnsZone.objects.select_related("owner").prefetch_related("records")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return (qs.filter(owner__parent=user) | qs.filter(owner=user)).distinct()
    return qs.filter(owner=user)
