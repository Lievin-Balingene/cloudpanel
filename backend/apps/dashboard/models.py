"""Historique des ressources serveur."""
from __future__ import annotations

from django.db import models


class ResourceSnapshot(models.Model):
    collected_at = models.DateTimeField(db_index=True)
    cpu_percent = models.FloatField()
    ram_percent = models.FloatField()
    ram_used = models.BigIntegerField()
    ram_total = models.BigIntegerField()
    disk_percent = models.FloatField()
    disk_used = models.BigIntegerField()
    disk_total = models.BigIntegerField()
    load_1 = models.FloatField(null=True, blank=True)
    load_5 = models.FloatField(null=True, blank=True)
    load_15 = models.FloatField(null=True, blank=True)
    net_bytes_sent = models.BigIntegerField(default=0)
    net_bytes_recv = models.BigIntegerField(default=0)
    temperatures = models.JSONField(default=dict, blank=True)
    process_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-collected_at",)
        indexes = [
            models.Index(fields=["-collected_at"]),
        ]

    def __str__(self) -> str:
        return f"Snapshot {self.collected_at.isoformat()}"
