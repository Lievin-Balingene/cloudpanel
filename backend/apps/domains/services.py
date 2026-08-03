"""Services domaines : quotas, DNS, document root, vhosts."""
from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q

from apps.accounts.models import User
from apps.core.exceptions import QuotaExceeded, VZoneAPIException
from apps.dns.models import DnsRecord, DnsZone
from apps.dns.services import create_zone_with_defaults
from apps.domains.fsutils import (
    apply_tree_permissions,
    secure_directory,
    secure_file,
    try_chown_vzone,
)
from apps.domains.models import Domain, DomainRedirect, normalize_hostname
from apps.files.services import ensure_cpanel_tree, personal_home

logger = logging.getLogger(__name__)


def _default_ipv4() -> str | None:
    for key in ("VZONE_MAIL_PUBLIC_IP", "VZONE_PUBLIC_IP"):
        val = (getattr(settings, key, None) or "").strip()
        if val:
            return val
    return None


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
    limit = int(quota.domains or 0)
    # 0 = illimité (style cPanel / admin)
    if limit <= 0:
        return
    used = _count_domains(owner)
    if used >= limit:
        raise QuotaExceeded(
            detail=f"Quota de domaines atteint ({used}/{limit}).",
            extra={"limit": limit, "used": used},
        )


def default_document_root(
    owner: User,
    hostname: str,
    domain_type: str = Domain.DomainType.PRIMARY,
    parent: Domain | None = None,
) -> str:
    """
    Chemins style cPanel :
    - primary → ~/public_html
    - addon / subdomain → ~/domains/<hostname>/public_html
    - parked / alias → docroot du parent (sinon ~/public_html)
    """
    home = personal_home(owner)
    if domain_type in {Domain.DomainType.ALIAS, Domain.DomainType.PARKED}:
        if parent and parent.document_root:
            return parent.document_root
        return str(home / "public_html")
    if domain_type == Domain.DomainType.PRIMARY:
        return str(home / "public_html")
    # addon / subdomain : dossier dédié (hostname réel, pas underscored)
    return str(home / "domains" / hostname.lower() / "public_html")


def provision_document_root(docroot: str, *, hostname: str, domain_type: str) -> Path:
    """Crée le docroot avec permissions 755 et index.html de bienvenue."""
    root = Path(docroot)
    # Assure aussi l'arbre home parent
    secure_directory(root, 0o755)
    secure_directory(root / "cgi-bin", 0o755)
    # logs du site à côté du public_html si domains/...
    if root.name == "public_html" and root.parent.name != "admin":
        site_base = root.parent
        secure_directory(site_base / "logs", 0o755)

    index = root / "index.html"
    if not index.exists():
        index.write_text(
            "<!DOCTYPE html>\n"
            "<html lang=\"fr\"><head><meta charset=\"utf-8\">"
            f"<title>{hostname}</title>"
            "<style>body{font-family:system-ui,sans-serif;max-width:40rem;margin:4rem auto;padding:0 1rem;color:#2c3e50}"
            "h1{font-size:1.5rem}p{color:#6b7c8f}</style></head>"
            f"<body><h1>{hostname}</h1>"
            "<p>Document root V-zone Panel — déposez vos fichiers ici "
            "(ou liez une app Python/Node/PHP : elle aura la priorité).</p>"
            f"<p><small>Type&nbsp;: {domain_type}</small></p>"
            "</body></html>\n",
            encoding="utf-8",
        )
        secure_file(index, 0o644)

    apply_tree_permissions(root, dir_mode=0o755, file_mode=0o644)
    try_chown_vzone(root)
    return root


def _ensure_a_record(zone: DnsZone, name: str, ipv4: str | None) -> None:
    if not ipv4:
        return
    DnsRecord.objects.update_or_create(
        zone=zone,
        record_type="A",
        name=name,
        defaults={"content": ipv4, "ttl": zone.ttl_default, "is_active": True},
    )


def _sync_vhost_safe(domain: Domain | None = None, *, remove_name: str | None = None) -> None:
    try:
        from apps.domains.vhosts import remove_domain_vhost, sync_all_domain_vhosts, sync_domain_vhost

        if remove_name:
            remove_domain_vhost(remove_name)
            sync_all_domain_vhosts()
        elif domain is not None:
            sync_domain_vhost(domain)
        else:
            sync_all_domain_vhosts()
    except Exception:  # noqa: BLE001
        logger.exception("Sync vhost échoué")


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
    try:
        hostname = normalize_hostname(name)
    except DjangoValidationError as exc:
        messages = getattr(exc, "messages", None) or [str(exc)]
        raise VZoneAPIException(
            detail=str(messages[0]),
            code="invalid_hostname",
            status_code=400,
        ) from exc

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

    if not ipv4_address:
        ipv4_address = _default_ipv4()

    # Home cPanel + docroot
    try:
        ensure_cpanel_tree(personal_home(owner))
        docroot = document_root or default_document_root(
            owner, hostname, domain_type=domain_type, parent=parent
        )
        if domain_type not in {Domain.DomainType.ALIAS, Domain.DomainType.PARKED}:
            provision_document_root(docroot, hostname=hostname, domain_type=domain_type)
        else:
            Path(docroot).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        home = personal_home(owner)
        raise VZoneAPIException(
            detail=(
                f"Impossible d'écrire dans {home} ({exc}). "
                "Exécutez: sudo bash /opt/vzone-src/scripts/ensure-homes.sh"
            ),
            code="docroot_permission_denied",
            status_code=500,
        ) from exc

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
    transaction.on_commit(lambda: _sync_vhost_safe(domain))
    return domain


@transaction.atomic
def delete_domain(domain: Domain, *, remove_dns_zone: bool = False) -> None:
    zone = domain.dns_zone
    domain_name = domain.name
    docroot = domain.document_root
    domain_type = domain.domain_type
    domain.delete()
    if remove_dns_zone and zone and not Domain.objects.filter(dns_zone=zone).exists():
        if zone.name == domain_name:
            zone.delete()
    transaction.on_commit(lambda: _sync_vhost_safe(remove_name=domain_name))

    # Nettoyage FS addon/subdomain (pas le public_html principal)
    if (
        domain_type in {Domain.DomainType.ADDON, Domain.DomainType.SUBDOMAIN}
        and docroot
        and "domains" in Path(docroot).parts
    ):
        import shutil

        site_dir = Path(docroot).parent  # .../domains/hostname
        try:
            if site_dir.exists() and site_dir.name == domain_name.lower():
                shutil.rmtree(site_dir, ignore_errors=True)
        except OSError as exc:
            logger.warning("Nettoyage docroot %s: %s", site_dir, exc)


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


def refresh_web_routing() -> int:
    """API / hooks apps : régénère tous les vhosts (priorité apps)."""
    from apps.domains.vhosts import sync_all_domain_vhosts

    return sync_all_domain_vhosts()
