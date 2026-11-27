"""Jetons d'accès externes — équivalent Manage API Tokens (cPanel / WHM)."""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def hash_api_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_api_token() -> str:
    return "vzapi_" + secrets.token_urlsafe(32)


class ApiToken(models.Model):
    """Secret affiché une seule fois. Seul le hash SHA-256 est stocké."""

    class Audience(models.TextChoices):
        UAPI = "uapi", "Compte (UAPI)"
        WHM = "whm", "WHM"
        BOTH = "both", "WHM et compte"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_tokens",
    )
    name = models.CharField(max_length=80)
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    token_prefix = models.CharField(max_length=16)
    audience = models.CharField(max_length=8, choices=Audience.choices, default=Audience.UAPI)
    # ["*"] ou noms de fonctions : "listaccts", "DomainInfo.list_domains"
    scopes = models.JSONField(default=list)
    ip_allowlist = models.TextField(
        blank=True,
        default="",
        help_text="IP ou CIDR séparés par des virgules. Vide = toutes les IP.",
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_used_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=["user", "name"], name="panel_api_token_name_per_user"),
        ]

    def __str__(self) -> str:
        return f"{self.user.username}:{self.name}"

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @property
    def status(self) -> str:
        now = timezone.now()
        if self.revoked_at is not None:
            return "revoked"
        if self.expires_at is not None and self.expires_at <= now:
            return "expired"
        if self.suspended_at is not None:
            return "suspended"
        return "active"

    def allows(self, kind: str, func_name: str) -> bool:
        if kind == "whm" and self.audience == self.Audience.UAPI:
            return False
        if kind == "uapi" and self.audience == self.Audience.WHM:
            return False
        scopes = self.scopes or ["*"]
        if "*" in scopes:
            return True
        return func_name in scopes

    def touch(self, ip: str | None) -> None:
        self.last_used_at = timezone.now()
        self.last_used_ip = ip
        self.save(update_fields=["last_used_at", "last_used_ip"])

    @classmethod
    def issue(
        cls,
        *,
        user,
        name: str,
        audience: str,
        scopes: list[str],
        ip_allowlist: str = "",
        expires_in_days: int | None = None,
        expires_at=None,
    ) -> tuple[ApiToken, str]:
        raw = generate_api_token()
        expires = expires_at
        if expires is None and expires_in_days:
            expires = timezone.now() + timedelta(days=int(expires_in_days))
        token = cls.objects.create(
            user=user,
            name=name.strip()[:80],
            token_hash=hash_api_token(raw),
            token_prefix=raw[:12],
            audience=audience,
            scopes=scopes or ["*"],
            ip_allowlist=(ip_allowlist or "").strip(),
            expires_at=expires,
        )
        return token, raw
