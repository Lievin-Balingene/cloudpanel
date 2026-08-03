"""Services domaines : quotas, DNS, document root."""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from apps.accounts.models import User
from apps.core.exceptions import QuotaExceeded, VZoneAPIException
from apps.dns.models import DnsRecord, DnsZone
from apps.dns.services import create_zone_with_defaults
from apps.domains.models import Domain, DomainRedirect, normalize_hostname


def domains_queryset_for(user: User):
    qs = Domain.objects.select_related("owner", "parent", "dns_zone", "ssl")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(owner=user) | Q(owner__parent=user))
    return qs.filter(owner=user)


def _count_domains(owner: User) -> int:
    return Domain.objects.filter(
        owner=owner,
        domain_type__in={
            Domain.DomainType.PRIMARY,
            Domain.DomainType.ADDON,
            Domain.DomainType.PARKED,
            Domain.DomainType.ALIAS,
        },
    ).count()


def _assert_domain_quota(owner: User) -> None:
    quota = getattr(owner, "quota", None)
    if quota is None:
        return
    limit = quota.domains
    if limit == 0 and owner.role == User.Role.ADMINISTRATOR:
        return
    if limit > 0 and _count_domains(owner) >= limit:
        raise QuotaExceeded(
            detail="Quota de domaines atteint.",
            extra={"limit": limit, "used": _count_domains(owner)},
        )


def default_document_root(owner: User, hostname: str) -> str:
    root = Path(settings.VZONE_HOME_ROOT) / (owner.system_username or owner.username) / "public_html"
    if hostname:
        safe = hostname.replace(".", "_")
        root = root.parent / "domains" / safe / "public_html"
    return str(root)


def _ensure_a_record(zone: DnsZone, name: str, ipv4: str | None) -> None:
    if not ipv4:
        return
    DnsRecord.objects.update_or_create(
        zone=zone,
        record_type="A",
        name=name,
        defaults={"content": ipv4, "ttl": zone.ttl_default, "is_active": True},
    )


@transaction.atomic
def create_domain(
    *,
    name: str,
    owner: User,
    domain_type: str = Domain.DomainType.PRIMARY,
    parent: Domain | None = None,
    ipv4_address: str | None = None,
    ipv6_address: str | None = None,
    create_dns_zone: bool = True,
    document_root: str = "",
    notes: str = "",
) -> Domain:
    hostname = normalize_hostname(name)

    if Domain.objects.filter(name=hostname).exists():
        raise VZoneAPIException(
            detail="Ce domaine existe déjà.",
            code="domain_exists",
            status_code=400,
        )

    if domain_type in {
        Domain.DomainType.PRIMARY,
        Domain.DomainType.ADDON,
        Domain.DomainType.PARKED,
        Domain.DomainType.ALIAS,
    }:
        _assert_domain_quota(owner)

    if domain_type == Domain.DomainType.SUBDOMAIN:
        if parent is None:
            raise VZoneAPIException(
                detail="Domaine parent requis pour un sous-domaine.",
                code="parent_required",
                status_code=400,
            )
        if not hostname.endswith("." + parent.name):
            raise VZoneAPIException(
                detail="Le sous-domaine doit se terminer par le domaine parent.",
                code="invalid_subdomain",
                status_code=400,
            )

    if domain_type in {Domain.DomainType.ALIAS, Domain.DomainType.PARKED} and parent is None:
        raise VZoneAPIException(
            detail="Domaine cible requis pour alias/parked.",
            code="parent_required",
            status_code=400,
        )

    docroot = document_root or default_document_root(owner, hostname)
    Path(docroot).mkdir(parents=True, exist_ok=True)

    zone = None
    if create_dns_zone and domain_type in {
        Domain.DomainType.PRIMARY,
        Domain.DomainType.ADDON,
        Domain.DomainType.PARKED,
        Domain.DomainType.ALIAS,
    }:
        existing = DnsZone.objects.filter(name=hostname).first()
        if existing:
            zone = existing
        else:
            zone = create_zone_with_defaults(name=hostname, owner=owner)
        _ensure_a_record(zone, "@", ipv4_address)
        _ensure_a_record(zone, "www", ipv4_address)
        if ipv6_address:
            DnsRecord.objects.update_or_create(
                zone=zone,
                record_type="AAAA",
                name="@",
                defaults={"content": ipv6_address, "ttl": zone.ttl_default, "is_active": True},
            )
        zone.bump_serial()
    elif domain_type == Domain.DomainType.SUBDOMAIN and parent and parent.dns_zone_id:
        zone = parent.dns_zone
        label = hostname[: -(len(parent.name) + 1)] or "@"
        _ensure_a_record(zone, label, ipv4_address or parent.ipv4_address)
        zone.bump_serial()

    domain = Domain.objects.create(
        name=hostname,
        owner=owner,
        domain_type=domain_type,
        parent=parent,
        document_root=docroot,
        create_dns_zone=create_dns_zone,
        dns_zone=zone,
        ipv4_address=ipv4_address,
        ipv6_address=ipv6_address,
        notes=notes,
    )
    return domain


@transaction.atomic
def delete_domain(domain: Domain, *, remove_dns_zone: bool = False) -> None:
    zone = domain.dns_zone
    domain_name = domain.name
    domain.delete()
    if remove_dns_zone and zone and not Domain.objects.filter(dns_zone=zone).exists():
        if zone.name == domain_name:
            zone.delete()


def create_redirect(
    *,
    domain: Domain,
    source_path: str,
    destination_url: str,
    redirect_type: str = DomainRedirect.RedirectType.PERMANENT,
    wildcard: bool = False,
) -> DomainRedirect:
    path = source_path.strip() or "/"
    if not path.startswith("/"):
        path = "/" + path
    return DomainRedirect.objects.create(
        domain=domain,
        source_path=path,
        destination_url=destination_url,
        redirect_type=redirect_type,
        wildcard=wildcard,
    )
