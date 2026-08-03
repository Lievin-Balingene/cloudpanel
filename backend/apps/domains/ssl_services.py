"""Émission et renouvellement SSL (Let's Encrypt + certificats personnalisés)."""
from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import VZoneAPIException
from apps.domains.models import Domain, SslCertificate

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CertificateMaterial:
    certificate_pem: str
    private_key_pem: str
    chain_pem: str
    issued_at: datetime
    expires_at: datetime
    alt_names: list[str]


def ssl_storage_root() -> Path:
    root = Path(settings.VZONE_DATA_ROOT) / "ssl"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _parse_expiry(cert_pem: str) -> tuple[datetime, datetime, list[str]]:
    cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
    issued = cert.not_valid_before_utc.replace(tzinfo=dt_timezone.utc)
    expires = cert.not_valid_after_utc.replace(tzinfo=dt_timezone.utc)
    alt: list[str] = []
    try:
        ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        alt = ext.value.get_values_for_type(x509.DNSName)
    except x509.ExtensionNotFound:
        alt = []
    return issued, expires, alt


def issue_self_signed(domain_name: str, days: int = 90) -> CertificateMaterial:
    """Génère un certificat auto-signé (dev / secours local)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, domain_name)]
    )
    alt_names = [domain_name, f"www.{domain_name}"]
    now = datetime.now(tz=dt_timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=days))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(n) for n in alt_names]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    issued, expires, alts = _parse_expiry(cert_pem)
    return CertificateMaterial(
        certificate_pem=cert_pem,
        private_key_pem=key_pem,
        chain_pem=cert_pem,
        issued_at=issued,
        expires_at=expires,
        alt_names=alts,
    )


def issue_with_certbot(domain_name: str, email: str, webroot: Path) -> CertificateMaterial:
    """Émet un certificat via certbot (production Linux)."""
    certbot = shutil.which("certbot")
    if not certbot:
        raise VZoneAPIException(
            detail="certbot introuvable sur le serveur. Installez certbot ou utilisez un certificat personnalisé.",
            code="certbot_missing",
            status_code=503,
        )
    webroot.mkdir(parents=True, exist_ok=True)
    live_dir = Path("/etc/letsencrypt/live") / domain_name
    cmd = [
        certbot,
        "certonly",
        "--non-interactive",
        "--agree-tos",
        "--email",
        email,
        "--webroot",
        "-w",
        str(webroot),
        "-d",
        domain_name,
        "-d",
        f"www.{domain_name}",
        "--keep-until-expiring",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise VZoneAPIException(
            detail=f"Échec Let's Encrypt: {result.stderr.strip() or result.stdout.strip()}",
            code="letsencrypt_failed",
            status_code=502,
            extra={"stdout": result.stdout[-2000:], "stderr": result.stderr[-2000:]},
        )
    cert_pem = (live_dir / "cert.pem").read_text(encoding="utf-8")
    key_pem = (live_dir / "privkey.pem").read_text(encoding="utf-8")
    chain_pem = (live_dir / "fullchain.pem").read_text(encoding="utf-8")
    issued, expires, alts = _parse_expiry(cert_pem)
    return CertificateMaterial(
        certificate_pem=cert_pem,
        private_key_pem=key_pem,
        chain_pem=chain_pem,
        issued_at=issued,
        expires_at=expires,
        alt_names=alts,
    )


def persist_files(domain: Domain, material: CertificateMaterial) -> Path:
    target = ssl_storage_root() / domain.name
    target.mkdir(parents=True, exist_ok=True)
    (target / "cert.pem").write_text(material.certificate_pem, encoding="utf-8")
    (target / "privkey.pem").write_text(material.private_key_pem, encoding="utf-8")
    (target / "fullchain.pem").write_text(material.chain_pem, encoding="utf-8")
    return target


@transaction.atomic
def install_custom_certificate(
    domain: Domain,
    *,
    certificate_pem: str,
    private_key_pem: str,
    chain_pem: str = "",
    auto_renew: bool = False,
) -> SslCertificate:
    try:
        issued, expires, alts = _parse_expiry(certificate_pem)
    except Exception as exc:  # noqa: BLE001
        raise VZoneAPIException(
            detail=f"Certificat invalide: {exc}",
            code="invalid_certificate",
            status_code=400,
        ) from exc

    material = CertificateMaterial(
        certificate_pem=certificate_pem.strip(),
        private_key_pem=private_key_pem.strip(),
        chain_pem=(chain_pem or certificate_pem).strip(),
        issued_at=issued,
        expires_at=expires,
        alt_names=alts,
    )
    persist_files(domain, material)
    ssl, _ = SslCertificate.objects.update_or_create(
        domain=domain,
        defaults={
            "provider": SslCertificate.Provider.CUSTOM,
            "status": SslCertificate.Status.ACTIVE,
            "common_name": domain.name,
            "alt_names": material.alt_names,
            "certificate_pem": material.certificate_pem,
            "private_key_pem": material.private_key_pem,
            "chain_pem": material.chain_pem,
            "auto_renew": auto_renew,
            "issued_at": material.issued_at,
            "expires_at": material.expires_at,
            "last_error": "",
            "last_checked_at": timezone.now(),
        },
    )
    return ssl


@transaction.atomic
def issue_letsencrypt(domain: Domain, *, email: str | None = None) -> SslCertificate:
    ssl, _ = SslCertificate.objects.get_or_create(
        domain=domain,
        defaults={
            "provider": SslCertificate.Provider.LETSENCRYPT,
            "common_name": domain.name,
            "auto_renew": True,
        },
    )
    ssl.provider = SslCertificate.Provider.LETSENCRYPT
    ssl.status = SslCertificate.Status.ISSUING
    ssl.last_error = ""
    ssl.save(update_fields=["provider", "status", "last_error", "updated_at"])

    contact = email or domain.owner.email
    backend = getattr(settings, "VZONE_SSL_BACKEND", "auto")

    try:
        if backend == "selfsigned" or (
            backend == "auto" and not shutil.which("certbot")
        ):
            if backend == "auto" and not getattr(settings, "DEBUG", False):
                raise VZoneAPIException(
                    detail="certbot requis en production pour Let's Encrypt.",
                    code="certbot_missing",
                    status_code=503,
                )
            material = issue_self_signed(domain.name)
            logger.warning(
                "SSL self-signed utilisé pour %s (backend=%s)", domain.name, backend
            )
        else:
            webroot = Path(domain.document_root or ssl_storage_root() / "acme-webroot")
            material = issue_with_certbot(domain.name, contact, webroot)

        persist_files(domain, material)
        ssl.status = SslCertificate.Status.ACTIVE
        ssl.common_name = domain.name
        ssl.alt_names = material.alt_names
        ssl.certificate_pem = material.certificate_pem
        ssl.private_key_pem = material.private_key_pem
        ssl.chain_pem = material.chain_pem
        ssl.issued_at = material.issued_at
        ssl.expires_at = material.expires_at
        ssl.last_error = ""
        ssl.last_checked_at = timezone.now()
        ssl.save()
        return ssl
    except VZoneAPIException as exc:
        ssl.mark_failed(str(exc.detail))
        raise
    except Exception as exc:  # noqa: BLE001
        ssl.mark_failed(str(exc))
        raise VZoneAPIException(
            detail=f"Échec SSL: {exc}",
            code="ssl_issue_failed",
            status_code=500,
        ) from exc


def renew_due_certificates() -> dict:
    """Renouvelle les certificats Let's Encrypt proches de l'expiration."""
    cutoff = timezone.now() + timedelta(days=30)
    qs = SslCertificate.objects.filter(
        provider=SslCertificate.Provider.LETSENCRYPT,
        auto_renew=True,
        status=SslCertificate.Status.ACTIVE,
        expires_at__lte=cutoff,
    ).select_related("domain", "domain__owner")
    renewed = 0
    failed = 0
    for cert in qs:
        try:
            issue_letsencrypt(cert.domain, email=cert.domain.owner.email)
            renewed += 1
        except Exception:  # noqa: BLE001
            failed += 1
            logger.exception("Renouvellement SSL échoué pour %s", cert.domain.name)
    return {"renewed": renewed, "failed": failed, "checked": qs.count()}
