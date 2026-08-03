"""Modèles règles d'alerte et événements."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class AlertRule(models.Model):
    class Metric(models.TextChoices):
        CPU_PERCENT = "cpu_percent", "CPU %"
        RAM_PERCENT = "ram_percent", "RAM %"
        DISK_PERCENT = "disk_percent", "Disque %"
        LOAD_1 = "load_1", "Load 1m"
        SERVICE_DOWN = "service_down", "Service down"

    class Operator(models.TextChoices):
        GT = "gt", ">"
        GTE = "gte", ">="
        LT = "lt", "<"
        LTE = "lte", "<="
        EQ = "eq", "=="

    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        CRITICAL = "critical", "Critical"

    name = models.CharField(max_length=120)
    metric = models.CharField(max_length=32, choices=Metric.choices)
    operator = models.CharField(
        max_length=8,
        choices=Operator.choices,
        default=Operator.GTE,
    )
    threshold = models.FloatField(default=90.0)
    service_name = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Nom service pour metric=service_down (ex: redis, nginx).",
    )
    severity = models.CharField(
        max_length=16,
        choices=Severity.choices,
        default=Severity.WARNING,
    )
    cooldown_minutes = models.PositiveIntegerField(default=30)
    notify_email = models.BooleanField(default=True)
    recipients = models.TextField(
        blank=True,
        default="",
        help_text="E-mails séparés par des virgules. Vide = DEFAULT_FROM / admins.",
    )
    is_active = models.BooleanField(default=True)
    last_triggered_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alert_rules_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        indexes = [models.Index(fields=["is_active", "metric"])]

    def __str__(self) -> str:
        return self.name

    def recipient_list(self) -> list[str]:
        return [e.strip() for e in self.recipients.split(",") if e.strip()]


class AlertEvent(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Ouverte"
        ACKNOWLEDGED = "acknowledged", "Acquittée"
        RESOLVED = "resolved", "Résolue"

    rule = models.ForeignKey(
        AlertRule,
        on_delete=models.CASCADE,
        related_name="events",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    metric_value = models.FloatField(null=True, blank=True)
    message = models.TextField(blank=True, default="")
    notified = models.BooleanField(default=False)
    notified_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alert_events_acked",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self) -> str:
        return f"{self.rule_id}:{self.status}"
