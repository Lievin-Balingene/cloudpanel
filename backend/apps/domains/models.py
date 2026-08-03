"""Modèles domaines, alias, sous-domaines, parked et redirections."""
from __future__ import annotations

import re

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$"
)
LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def normalize_hostname(value: str) -> str:
    value = value.strip().lower().rstrip(".")
    if not DOMAIN_RE.match(value):
        raise ValidationError("Nom d'hôte invalide.")
    return value


class Domain(models.Model):
    """Domaine rattaché à un compte d'hébergement."""

    class DomainType(models.TextChoices):
        PRIMARY = "primary", "Domaine principal"
        ADDON = "addon", "Addon domain"
        SUBDOMAIN = "subdomain", "Sous-domaine"
        PARKED = "parked", "Parked / Alias de domaine"
        ALIAS = "alias", "Alias"

    name = models.CharField(max_length=255, unique=True, db_index=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="domains",
    )
    domain_type = models.CharField(
        max_length=16,
        choices=DomainType.choices,
        default=DomainType.PRIMARY,
        db_index=True,
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        help_text="Domaine parent pour sous-domaine / alias.",
    )
    document_root = models.CharField(max_length=512, blank=True, default="")
    is_active = models.BooleanField(default=True)
    is_suspended = models.BooleanField(default=False)
    create_dns_zone = models.BooleanField(default=True)
    dns_zone = models.ForeignKey(
        "dns.DnsZone",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hosted_domains",
    )
    ipv4_address = models.GenericIPAddressField(protocol="IPv4", null=True, blank=True)
    ipv6_address = models.GenericIPAddressField(protocol="IPv6", null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        indexes = [
            models.Index(fields=["owner", "domain_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.domain_type})"

    def clean(self) -> None:
        self.name = normalize_hostname(self.name)
        if self.domain_type == self.DomainType.SUBDOMAIN and not self.parent_id:
            raise ValidationError({"parent": "Un sous-domaine nécessite un domaine parent."})
        if self.domain_type in {self.DomainType.ALIAS, self.DomainType.PARKED} and not self.parent_id:
            raise ValidationError({"parent": "Alias/Parked nécessitent un domaine cible."})


class DomainRedirect(models.Model):
    """Redirection HTTP associée à un domaine."""

    class RedirectType(models.TextChoices):
        PERMANENT = "301", "301 Permanent"
        TEMPORARY = "302", "302 Temporary"

    domain = models.ForeignKey(Domain, on_delete=models.CASCADE, related_name="redirects")
    source_path = models.CharField(max_length=512, default="/")
    destination_url = models.URLField(max_length=2048)
    redirect_type = models.CharField(
        max_length=3,
        choices=RedirectType.choices,
        default=RedirectType.PERMANENT,
    )
    wildcard = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("domain_id", "source_path")
        unique_together = ("domain", "source_path")

    def __str__(self) -> str:
        return f"{self.domain.name}{self.source_path} → {self.destination_url}"


class SslCertificate(models.Model):
    """Certificat SSL lié à un domaine."""

    class Provider(models.TextChoices):
        LETSENCRYPT = "letsencrypt", "Let's Encrypt"
        CUSTOM = "custom", "Personnalisé"

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        ISSUING = "issuing", "Émission"
        ACTIVE = "active", "Actif"
        EXPIRED = "expired", "Expiré"
        FAILED = "failed", "Échec"
        REVOKED = "revoked", "Révoqué"

    domain = models.OneToOneField(Domain, on_delete=models.CASCADE, related_name="ssl")
    provider = models.CharField(max_length=32, choices=Provider.choices, default=Provider.LETSENCRYPT)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    common_name = models.CharField(max_length=255, blank=True, default="")
    alt_names = models.JSONField(default=list, blank=True)
    certificate_pem = models.TextField(blank=True, default="")
    private_key_pem = models.TextField(blank=True, default="")
    chain_pem = models.TextField(blank=True, default="")
    auto_renew = models.BooleanField(default=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    last_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Certificat SSL"
        verbose_name_plural = "Certificats SSL"

    def __str__(self) -> str:
        return f"SSL {self.domain.name} [{self.status}]"

    @property
    def is_expiring_soon(self) -> bool:
        if not self.expires_at:
            return False
        return self.expires_at <= timezone.now() + timedelta(days=30)

    def mark_failed(self, message: str) -> None:
        self.status = self.Status.FAILED
        self.last_error = message[:4000]
        self.last_checked_at = timezone.now()
        self.save(
            update_fields=["status", "last_error", "last_checked_at", "updated_at"]
        )
