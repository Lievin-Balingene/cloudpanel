"""Modèles sauvegardes compte utilisateur."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class BackupArchive(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        RUNNING = "running", "En cours"
        COMPLETED = "completed", "Terminée"
        FAILED = "failed", "Échouée"
        RESTORING = "restoring", "Restauration"
        RESTORED = "restored", "Restaurée"

    class BackupType(models.TextChoices):
        FULL = "full", "Complète"
        HOME = "home", "Fichiers"
        DATABASES = "databases", "Bases"
        EMAIL = "email", "Email"
        CUSTOM = "custom", "Personnalisée"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="backup_archives",
    )
    name = models.CharField(max_length=64, db_index=True)
    label = models.CharField(max_length=120, blank=True, default="")
    backup_type = models.CharField(
        max_length=16,
        choices=BackupType.choices,
        default=BackupType.FULL,
    )
    includes = models.JSONField(
        default=list,
        blank=True,
        help_text='Composants inclus, ex: ["home", "databases", "email"].',
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    file_name = models.CharField(max_length=255, blank=True, default="")
    size_bytes = models.BigIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True, default="")
    last_error = models.TextField(blank=True, default="")
    notes = models.CharField(max_length=255, blank=True, default="")
    completed_at = models.DateTimeField(null=True, blank=True)
    restored_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        unique_together = ("owner", "name")
        indexes = [models.Index(fields=["owner", "status"])]

    def __str__(self) -> str:
        return f"{self.owner.username}/{self.name}"


class BackupSchedule(models.Model):
    class Frequency(models.TextChoices):
        DAILY = "daily", "Quotidien"
        WEEKLY = "weekly", "Hebdomadaire"
        MONTHLY = "monthly", "Mensuel"

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="backup_schedule",
    )
    frequency = models.CharField(
        max_length=16,
        choices=Frequency.choices,
        default=Frequency.WEEKLY,
    )
    includes = models.JSONField(default=list, blank=True)
    hour = models.PositiveSmallIntegerField(default=2)
    weekday = models.PositiveSmallIntegerField(
        default=0,
        help_text="0=lundi … 6=dimanche (hebdomadaire).",
    )
    is_active = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("owner__username",)

    def __str__(self) -> str:
        return f"Schedule({self.owner.username}, {self.frequency})"


class BackupEventLog(models.Model):
    class Event(models.TextChoices):
        CREATE = "create", "Create"
        COMPLETE = "complete", "Complete"
        RESTORE = "restore", "Restore"
        DELETE = "delete", "Delete"
        DOWNLOAD = "download", "Download"
        SCHEDULE = "schedule", "Schedule"
        FAIL = "fail", "Fail"

    archive = models.ForeignKey(
        BackupArchive,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="event_logs",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="backup_event_logs",
    )
    event_type = models.CharField(max_length=16, choices=Event.choices)
    success = models.BooleanField(default=True)
    message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.owner_id}:{self.event_type}"
