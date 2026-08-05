"""Modèles tâches cron (style cPanel)."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class CronJob(models.Model):
    """Une ligne de crontab rattachée à un compte d'hébergement."""

    class Common(models.TextChoices):
        CUSTOM = "custom", "Custom (défini ci‑dessous)"
        ONCE_PER_MINUTE = "once_per_minute", "Une fois par minute (* * * * *)"
        ONCE_PER_FIVE = "once_per_five", "Toutes les 5 minutes (*/5 * * * *)"
        TWICE_PER_HOUR = "twice_per_hour", "Deux fois par heure (0,30 * * * *)"
        ONCE_PER_HOUR = "once_per_hour", "Une fois par heure (0 * * * *)"
        TWICE_PER_DAY = "twice_per_day", "Deux fois par jour (0 0,12 * * *)"
        ONCE_PER_DAY = "once_per_day", "Une fois par jour (0 0 * * *)"
        ONCE_PER_WEEK = "once_per_week", "Une fois par semaine (0 0 * * 0)"
        ONCE_PER_MONTH = "once_per_month", "Une fois par mois (0 0 1 * *)"
        ONCE_PER_YEAR = "once_per_year", "Une fois par an (0 0 1 1 *)"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cron_jobs",
    )
    common = models.CharField(
        max_length=32,
        choices=Common.choices,
        default=Common.CUSTOM,
    )
    minute = models.CharField(max_length=64, default="0")
    hour = models.CharField(max_length=64, default="*")
    day = models.CharField(max_length=64, default="*")
    month = models.CharField(max_length=64, default="*")
    weekday = models.CharField(max_length=64, default="*")
    command = models.TextField()
    email_to = models.EmailField(
        blank=True,
        default="",
        help_text="MAILTO — recevoir la sortie de la commande (optionnel).",
    )
    label = models.CharField(max_length=120, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("owner_id", "id")
        indexes = [
            models.Index(fields=["owner", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"CronJob({self.owner_id}:{self.schedule_line})"

    @property
    def schedule_line(self) -> str:
        return f"{self.minute} {self.hour} {self.day} {self.month} {self.weekday}"
