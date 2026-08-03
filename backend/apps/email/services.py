"""Services e-mail : boîtes, forwarders, DKIM/SPF/DMARC, maps Postfix/Dovecot."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet

from apps.accounts.models import User
from apps.core.exceptions import QuotaExceeded, VZoneAPIException
from apps.dns.models import DnsRecord, DnsZone
from apps.dns.services import create_zone_with_defaults
from apps.email.models import (
    Autoresponder,
    Mailbox,
    MailDomain,
    MailFilter,
    MailForwarder,
    MailingList,
)
from apps.files.services import user_home

logger = logging.getLogger(__name__)

LOCAL_PART_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,62}$", re.I)


def mail_domains_qs(user: User) -> QuerySet[MailDomain]:
    qs = MailDomain.objects.select_related("owner", "domain")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(owner=user) | Q(owner__parent=user))
    return qs.filter(owner=user)


def mailboxes_qs(user: User) -> QuerySet[Mailbox]:
    qs = Mailbox.objects.select_related("mail_domain", "mail_domain__owner")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(mail_domain__owner=user) | Q(mail_domain__owner__parent=user))
    return qs.filter(mail_domain__owner=user)


def _assert_email_quota(owner: User) -> None:
    quota = getattr(owner, "quota", None)
    if quota is None:
        return
    limit = quota.emails
    if limit == 0 and owner.role == User.Role.ADMINISTRATOR:
        return
    used = Mailbox.objects.filter(mail_domain__owner=owner).count()
    if limit > 0 and used >= limit:
        raise QuotaExceeded(
            detail="Quota de comptes e-mail atteint.",
            extra={"limit": limit, "used": used},
        )


def mail_storage_root() -> Path:
    root = Path(getattr(settings, "VZONE_MAIL_MAPS_DIR", None) or (Path(settings.VZONE_DATA_ROOT) / "mail"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def mailbox_maildir(owner: User, address: str) -> Path:
    safe = address.replace("@", "_at_").replace(".", "_")
    path = user_home(owner) / "mail" / safe
    path.mkdir(parents=True, exist_ok=True)
    for sub in ("cur", "new", "tmp"):
        (path / sub).mkdir(exist_ok=True)
    return path


def generate_dkim_keys() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    # DNS TXT value: strip PEM headers
    public_b64 = "".join(
        line for line in public_pem.splitlines() if not line.startswith("-----")
    )
    return private_pem, public_b64


def default_spf(domain_name: str) -> str:
    return f"v=spf1 mx a:{domain_name} ~all"


def dmarc_record(policy: str, rua: str, domain_name: str) -> str:
    rua_part = f" rua=mailto:{rua}" if rua else f" rua=mailto:dmarc@{domain_name}"
    return f"v=DMARC1; p={policy};{rua_part}; adkim=s; aspf=s"


def ensure_dns_zone_for_mail(owner: User, domain_name: str) -> DnsZone:
    zone = DnsZone.objects.filter(name=domain_name).first()
    if zone:
        return zone
    return create_zone_with_defaults(name=domain_name, owner=owner)


def upsert_txt(zone: DnsZone, name: str, content: str) -> None:
    DnsRecord.objects.update_or_create(
        zone=zone,
        record_type="TXT",
        name=name,
        defaults={"content": content, "ttl": 3600, "is_active": True},
    )


def upsert_mx(zone: DnsZone, content: str = "mail", priority: int = 10) -> None:
    DnsRecord.objects.update_or_create(
        zone=zone,
        record_type="MX",
        name="@",
        defaults={
            "content": content if content.endswith(".") else f"{content}.{zone.name}.",
            "priority": priority,
            "ttl": 3600,
            "is_active": True,
        },
    )


@transaction.atomic
def sync_mail_dns(mail_domain: MailDomain) -> dict:
    zone = ensure_dns_zone_for_mail(mail_domain.owner, mail_domain.name)
    if not mail_domain.spf_record:
        mail_domain.spf_record = default_spf(mail_domain.name)
    upsert_txt(zone, "@", mail_domain.spf_record)
    upsert_mx(zone, "mail")

    dkim_name = f"{mail_domain.dkim_selector}._domainkey"
    dkim_value = ""
    if mail_domain.dkim_enabled and mail_domain.dkim_public_key:
        dkim_value = f"v=DKIM1; k=rsa; p={mail_domain.dkim_public_key}"
        upsert_txt(zone, dkim_name, dkim_value)

    dmarc_value = dmarc_record(
        mail_domain.dmarc_policy,
        mail_domain.dmarc_rua,
        mail_domain.name,
    )
    upsert_txt(zone, "_dmarc", dmarc_value)
    zone.bump_serial()
    mail_domain.save(update_fields=["spf_record", "updated_at"])
    return {
        "spf": mail_domain.spf_record,
        "dkim": dkim_value or None,
        "dmarc": dmarc_value,
        "mx": f"10 mail.{mail_domain.name}",
        "zone": zone.name,
    }


@transaction.atomic
def enable_dkim(mail_domain: MailDomain, selector: str = "default") -> MailDomain:
    private_pem, public_b64 = generate_dkim_keys()
    mail_domain.dkim_enabled = True
    mail_domain.dkim_selector = selector or "default"
    mail_domain.dkim_private_key = private_pem
    mail_domain.dkim_public_key = public_b64
    mail_domain.save()
    # Store private key on disk for OpenDKIM
    key_dir = mail_storage_root() / "dkim" / mail_domain.name
    key_dir.mkdir(parents=True, exist_ok=True)
    (key_dir / f"{mail_domain.dkim_selector}.private").write_text(private_pem, encoding="utf-8")
    (key_dir / f"{mail_domain.dkim_selector}.txt").write_text(
        f"v=DKIM1; k=rsa; p={public_b64}",
        encoding="utf-8",
    )
    sync_mail_dns(mail_domain)
    return mail_domain


def write_mail_maps() -> Path:
    """Exporte maps virtuelles Postfix/Dovecot."""
    root = mail_storage_root()
    passwd = root / "vmailbox"
    aliases = root / "valiases"
    passwd_lines: list[str] = []
    alias_lines: list[str] = []

    for box in Mailbox.objects.filter(is_active=True, is_suspended=False).select_related("mail_domain"):
        # format: user@domain:password:uid:gid::maildir::
        passwd_lines.append(
            f"{box.address}:{box.password_hash}::::{box.maildir}::"
        )

    for fwd in MailForwarder.objects.filter(is_active=True).select_related("mail_domain"):
        dests = ",".join(fwd.destinations)
        if fwd.keep_copy:
            dests = f"{fwd.address},{dests}" if dests else fwd.address
        alias_lines.append(f"{fwd.address}: {dests}")

    for lst in MailingList.objects.filter(is_active=True).select_related("mail_domain"):
        members = ",".join(lst.members)
        alias_lines.append(f"{lst.address}: {members}")

    for md in MailDomain.objects.filter(is_active=True):
        if md.catch_all:
            alias_lines.append(f"@{md.name}: {md.catch_all}")

    passwd.write_text("\n".join(passwd_lines) + ("\n" if passwd_lines else ""), encoding="utf-8")
    aliases.write_text("\n".join(alias_lines) + ("\n" if alias_lines else ""), encoding="utf-8")
    return root


@transaction.atomic
def create_mail_domain(
    *,
    owner: User,
    name: str,
    domain_id: int | None = None,
    max_quota_mb: int = 1024,
    enable_dns: bool = True,
) -> MailDomain:
    from apps.domains.models import Domain

    hostname = name.strip().lower().rstrip(".")
    if MailDomain.objects.filter(name=hostname).exists():
        raise VZoneAPIException(detail="Domaine mail déjà existant.", code="exists", status_code=400)
    domain_obj = None
    if domain_id:
        domain_obj = Domain.objects.filter(pk=domain_id, owner=owner).first()
        if domain_obj is None and owner.role == User.Role.ADMINISTRATOR:
            domain_obj = Domain.objects.filter(pk=domain_id).first()
    md = MailDomain.objects.create(
        owner=owner,
        name=hostname,
        domain=domain_obj,
        max_quota_mb=max_quota_mb,
        spf_record=default_spf(hostname),
    )
    if enable_dns:
        sync_mail_dns(md)
    write_mail_maps()
    return md


@transaction.atomic
def create_mailbox(
    *,
    mail_domain: MailDomain,
    local_part: str,
    password: str,
    quota_mb: int | None = None,
    notes: str = "",
) -> Mailbox:
    local = local_part.strip().lower()
    if not LOCAL_PART_RE.match(local):
        raise VZoneAPIException(detail="Partie locale invalide.", code="invalid_local", status_code=400)
    if len(password) < 8:
        raise VZoneAPIException(detail="Mot de passe trop court (min 8).", code="weak_password", status_code=400)
    _assert_email_quota(mail_domain.owner)
    if Mailbox.objects.filter(mail_domain=mail_domain, local_part=local).exists():
        raise VZoneAPIException(detail="Cette boîte existe déjà.", code="exists", status_code=400)
    q = quota_mb or min(250, mail_domain.max_quota_mb)
    q = min(q, mail_domain.max_quota_mb)
    address = f"{local}@{mail_domain.name}"
    maildir = mailbox_maildir(mail_domain.owner, address)
    box = Mailbox(
        mail_domain=mail_domain,
        local_part=local,
        quota_mb=q,
        maildir=str(maildir),
        notes=notes,
    )
    box.set_password(password)
    box.save()
    Autoresponder.objects.get_or_create(mailbox=box)
    write_mail_maps()
    return box


@transaction.atomic
def update_mailbox(
    box: Mailbox,
    *,
    password: str | None = None,
    quota_mb: int | None = None,
    is_active: bool | None = None,
    notes: str | None = None,
) -> Mailbox:
    if password is not None:
        if len(password) < 8:
            raise VZoneAPIException(detail="Mot de passe trop court.", code="weak_password", status_code=400)
        box.set_password(password)
    if quota_mb is not None:
        box.quota_mb = min(quota_mb, box.mail_domain.max_quota_mb)
    if is_active is not None:
        box.is_active = is_active
    if notes is not None:
        box.notes = notes
    box.save()
    write_mail_maps()
    return box


@transaction.atomic
def suspend_mailbox(box: Mailbox, suspended: bool = True) -> Mailbox:
    box.is_suspended = suspended
    box.is_active = not suspended
    box.save(update_fields=["is_suspended", "is_active", "updated_at"])
    write_mail_maps()
    return box


@transaction.atomic
def delete_mailbox(box: Mailbox) -> None:
    box.delete()
    write_mail_maps()


@transaction.atomic
def create_forwarder(
    *,
    mail_domain: MailDomain,
    local_part: str,
    destinations: list[str],
    keep_copy: bool = False,
) -> MailForwarder:
    local = local_part.strip().lower()
    if not LOCAL_PART_RE.match(local) and local != "*":
        raise VZoneAPIException(detail="Alias invalide.", code="invalid_local", status_code=400)
    dests = [d.strip().lower() for d in destinations if d.strip()]
    if not dests:
        raise VZoneAPIException(detail="Au moins une destination requise.", code="no_destination", status_code=400)
    fwd, _ = MailForwarder.objects.update_or_create(
        mail_domain=mail_domain,
        local_part=local,
        defaults={"destinations": dests, "keep_copy": keep_copy, "is_active": True},
    )
    write_mail_maps()
    return fwd


@transaction.atomic
def set_autoresponder(
    box: Mailbox,
    *,
    is_active: bool,
    subject: str,
    body: str,
    start_at=None,
    end_at=None,
    interval_hours: int = 24,
) -> Autoresponder:
    ar, _ = Autoresponder.objects.get_or_create(mailbox=box)
    ar.is_active = is_active
    ar.subject = subject
    ar.body = body
    ar.start_at = start_at
    ar.end_at = end_at
    ar.interval_hours = interval_hours
    ar.save()
    return ar


@transaction.atomic
def create_filter(
    box: Mailbox,
    *,
    name: str,
    match_field: str,
    match_op: str,
    match_value: str,
    action: str,
    action_value: str = "",
    priority: int = 100,
) -> MailFilter:
    return MailFilter.objects.create(
        mailbox=box,
        name=name,
        match_field=match_field,
        match_op=match_op,
        match_value=match_value,
        action=action,
        action_value=action_value,
        priority=priority,
    )


@transaction.atomic
def create_mailing_list(
    mail_domain: MailDomain,
    *,
    local_part: str,
    members: list[str],
) -> MailingList:
    local = local_part.strip().lower()
    if not LOCAL_PART_RE.match(local):
        raise VZoneAPIException(detail="Nom de liste invalide.", code="invalid_local", status_code=400)
    cleaned = [m.strip().lower() for m in members if m.strip()]
    lst, _ = MailingList.objects.update_or_create(
        mail_domain=mail_domain,
        local_part=local,
        defaults={"members": cleaned, "is_active": True},
    )
    write_mail_maps()
    return lst


def webmail_url() -> str:
    return getattr(settings, "VZONE_WEBMAIL_URL", "/webmail/")
