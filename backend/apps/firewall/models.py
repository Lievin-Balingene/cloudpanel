"""Modèles firewall et Fail2Ban."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class FirewallRule(models.Model):
    class Action(models.TextChoices):
        ALLOW = "allow", "Allow"
        DENY = "deny", "Deny"

    class Protocol(models.TextChoices):
        TCP = "tcp", "TCP"
        UDP = "udp", "UDP"
        ANY = "any", "Any"

    class Direction(models.TextChoices):
        IN = "in", "Inbound"
        OUT = "out", "Outbound"

    name = models.CharField(max_length=120)
    action = models.CharField(max_length=8, choices=Action.choices, default=Action.ALLOW)
    protocol = models.CharField(max_length=8, choices=Protocol.choices, default=Protocol.TCP)
    direction = models.CharField(max_length=8, choices=Direction.choices, default=Direction.IN)
    port_start = models.PositiveIntegerField(null=True, blank=True)
    port_end = models.PositiveIntegerField(null=True, blank=True)
    source_cidr = models.CharField(max_length=64, blank=True, default="", help_text="IP ou CIDR source")
    dest_cidr = models.CharField(max_length=64, blank=True, default="", help_text="IP ou CIDR destination")
    priority = models.PositiveIntegerField(default=100)
    is_enabled = models.BooleanField(default=True)
    is_applied = models.BooleanField(default=False)
    notes = models.CharField(max_length=255, blank=True, default="")
    last_error = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="firewall_rules_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("priority", "name")
        indexes = [models.Index(fields=["is_enabled", "action"])]

    def __str__(self) -> str:
        return self.name


class Fail2BanJail(models.Model):
    """État connu d'une jail (sync mock ou live)."""

    name = models.CharField(max_length=64, unique=True)
    is_enabled = models.BooleanField(default=True)
    filter_name = models.CharField(max_length=64, blank=True, default="")
    max_retry = models.PositiveIntegerField(default=5)
    find_time = models.PositiveIntegerField(default=600, help_text="Secondes")
    ban_time = models.PositiveIntegerField(default=3600, help_text="Secondes")
    currently_banned = models.PositiveIntegerField(default=0)
    total_banned = models.PositiveIntegerField(default=0)
    notes = models.CharField(max_length=255, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Fail2BanBan(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Actif"
        UNBANNED = "unbanned", "Débanni"

    jail = models.ForeignKey(
        Fail2BanJail,
        on_delete=models.CASCADE,
        related_name="bans",
    )
    ip_address = models.GenericIPAddressField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    reason = models.CharField(max_length=255, blank=True, default="")
    banned_at = models.DateTimeField(auto_now_add=True)
    unbanned_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fail2ban_bans_created",
    )

    class Meta:
        ordering = ("-banned_at",)
        indexes = [models.Index(fields=["status", "ip_address"])]

    def __str__(self) -> str:
        return f"{self.jail_id}:{self.ip_address}"


class FirewallEventLog(models.Model):
    class Event(models.TextChoices):
        RULE_CREATE = "rule_create", "Rule create"
        RULE_UPDATE = "rule_update", "Rule update"
        RULE_DELETE = "rule_delete", "Rule delete"
        RULE_APPLY = "rule_apply", "Rule apply"
        BAN = "ban", "Ban"
        UNBAN = "unban", "Unban"
        SYNC = "sync", "Sync"
        FAIL = "fail", "Fail"

    event_type = models.CharField(max_length=16, choices=Event.choices)
    success = models.BooleanField(default=True)
    message = models.TextField(blank=True, default="")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="firewall_event_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.event_type}:{self.created_at}"
