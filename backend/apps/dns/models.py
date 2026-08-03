"""Modèles zones et enregistrements DNS."""
from __future__ import annotations

import re
import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


RECORD_TYPES = (
    ("A", "A"),
    ("AAAA", "AAAA"),
    ("CNAME", "CNAME"),
    ("TXT", "TXT"),
    ("MX", "MX"),
    ("SRV", "SRV"),
    ("CAA", "CAA"),
    ("NS", "NS"),
)


def normalize_zone_name(name: str) -> str:
    name = name.strip().lower().rstrip(".")
    if not re.match(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$", name):
        raise ValidationError("Nom de zone DNS invalide.")
    return name


class DnsZone(models.Model):
    name = models.CharField(max_length=255, unique=True, db_index=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dns_zones",
    )
    ttl_default = models.PositiveIntegerField(default=14400)
    soa_primary_ns = models.CharField(max_length=255, default="ns1.vzone.local.")
    soa_admin_email = models.CharField(max_length=255, default="hostmaster.vzone.local.")
    soa_serial = models.PositiveIntegerField(default=1)
    soa_refresh = models.PositiveIntegerField(default=3600)
    soa_retry = models.PositiveIntegerField(default=1800)
    soa_expire = models.PositiveIntegerField(default=1209600)
    soa_minimum = models.PositiveIntegerField(default=86400)
    dnssec_enabled = models.BooleanField(default=False)
    dnssec_algorithm = models.CharField(max_length=32, blank=True, default="")
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        self.name = normalize_zone_name(self.name)

    def bump_serial(self) -> None:
        today = int(time.strftime("%Y%m%d"))
        base = today * 100
        if self.soa_serial // 100 == today:
            self.soa_serial += 1
        else:
            self.soa_serial = base + 1
        self.save(update_fields=["soa_serial", "updated_at"])


class DnsRecord(models.Model):
    zone = models.ForeignKey(DnsZone, on_delete=models.CASCADE, related_name="records")
    record_type = models.CharField(max_length=8, choices=RECORD_TYPES, db_index=True)
    name = models.CharField(
        max_length=255,
        help_text="Nom relatif (@ pour apex, www, mail…).",
    )
    content = models.TextField()
    ttl = models.PositiveIntegerField(null=True, blank=True)
    priority = models.PositiveIntegerField(null=True, blank=True)
    weight = models.PositiveIntegerField(null=True, blank=True)
    port = models.PositiveIntegerField(null=True, blank=True)
    flags = models.PositiveIntegerField(null=True, blank=True, help_text="CAA flags")
    tag = models.CharField(max_length=32, blank=True, default="", help_text="CAA tag")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("record_type", "name")
        indexes = [
            models.Index(fields=["zone", "record_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.record_type} {self.name}.{self.zone.name}"

    def clean(self) -> None:
        self.name = self.name.strip() or "@"
        rtype = self.record_type
        if rtype in {"MX", "SRV"} and self.priority is None:
            raise ValidationError({"priority": "Priorité requise pour MX/SRV."})
        if rtype == "SRV" and (self.weight is None or self.port is None):
            raise ValidationError("Weight et port requis pour SRV.")
        if rtype == "CAA" and not self.tag:
            raise ValidationError({"tag": "Tag CAA requis (issue, issuewild, iodef)."})
        if rtype == "CNAME" and self.name in {"@", ""}:
            raise ValidationError({"name": "CNAME sur l'apex non recommandé / interdit ici."})
