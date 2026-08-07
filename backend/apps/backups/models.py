"""Modèles sauvegardes Restic + Rclone."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class BackupDestination(models.Model):
    """Destination de stockage (abstraction Rclone)."""

    class Provider(models.TextChoices):
        LOCAL = "local", "Local"
        SFTP = "sftp", "SFTP"
        S3 = "s3", "Amazon S3 compatible"
        B2 = "b2", "Backblaze B2"
        R2 = "r2", "Cloudflare R2"
        GDRIVE = "gdrive", "Google Drive"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="backup_destinations",
        null=True,
        blank=True,
        help_text="Null = destination globale admin.",
    )
    name = models.CharField(max_length=64)
    label = models.CharField(max_length=120, blank=True, default="")
    provider = models.CharField(max_length=16, choices=Provider.choices, default=Provider.LOCAL)
    # Config provider (sans secrets en clair) — secrets chiffrés à part
    config = models.JSONField(default=dict, blank=True)
    # Mot de passe dépôt Restic (Fernet)
    restic_password_secret = models.TextField(blank=True, default="")
    # Secrets provider (clé S3, token B2, password SFTP…) chiffrés JSON
    credentials_secret = models.TextField(blank=True, default="")
    rclone_remote = models.CharField(max_length=64, blank=True, default="")
    repository_uri = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text="URI Restic, ex. /path ou rclone:remote:bucket/path",
    )
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        unique_together = ("owner", "name")
        indexes = [models.Index(fields=["provider", "is_active"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.provider})"


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
        INCREMENTAL = "incremental", "Incrémentale"
        HOME = "home", "Fichiers"
        DATABASES = "databases", "Bases"
        EMAIL = "email", "Email"
        CUSTOM = "custom", "Personnalisée"

    class Trigger(models.TextChoices):
        MANUAL = "manual", "Manuel"
        SCHEDULED = "scheduled", "Planifié"
        API = "api", "API"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="backup_archives",
    )
    destination = models.ForeignKey(
        BackupDestination,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archives",
    )
    name = models.CharField(max_length=64, db_index=True)
    label = models.CharField(max_length=120, blank=True, default="")
    backup_type = models.CharField(
        max_length=16,
        choices=BackupType.choices,
        default=BackupType.FULL,
    )
    trigger = models.CharField(
        max_length=16,
        choices=Trigger.choices,
        default=Trigger.MANUAL,
    )
    includes = models.JSONField(
        default=list,
        blank=True,
        help_text='Composants inclus, ex: ["home", "databases", "email"].',
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    # Restic snapshot id (hex)
    snapshot_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    parent_snapshot_id = models.CharField(max_length=64, blank=True, default="")
    file_name = models.CharField(max_length=255, blank=True, default="")
    size_bytes = models.BigIntegerField(default=0)
    files_new = models.PositiveIntegerField(default=0)
    files_changed = models.PositiveIntegerField(default=0)
    files_unmodified = models.PositiveIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True, default="")
    progress = models.PositiveSmallIntegerField(default=0)
    duration_seconds = models.PositiveIntegerField(default=0)
    log = models.TextField(blank=True, default="")
    last_error = models.TextField(blank=True, default="")
    notes = models.CharField(max_length=255, blank=True, default="")
    celery_task_id = models.CharField(max_length=64, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    restored_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        unique_together = ("owner", "name")
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["snapshot_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.owner.username}/{self.name}"

    def append_log(self, line: str) -> None:
        stamp = ""
        try:
            from django.utils import timezone

            stamp = timezone.now().strftime("%H:%M:%S")
        except Exception:  # noqa: BLE001
            pass
        prefix = f"[{stamp}] " if stamp else ""
        chunk = f"{prefix}{line}".rstrip()
        self.log = ((self.log or "") + chunk + "\n")[-50000:]


class BackupSchedule(models.Model):
    class Frequency(models.TextChoices):
        HOURLY = "hourly", "Horaire"
        DAILY = "daily", "Quotidien"
        WEEKLY = "weekly", "Hebdomadaire"
        MONTHLY = "monthly", "Mensuel"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="backup_schedules",
    )
    destination = models.ForeignKey(
        BackupDestination,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schedules",
    )
    name = models.CharField(max_length=64, blank=True, default="")
    frequency = models.CharField(
        max_length=16,
        choices=Frequency.choices,
        default=Frequency.WEEKLY,
    )
    includes = models.JSONField(default=list, blank=True)
    hour = models.PositiveSmallIntegerField(default=2)
    minute = models.PositiveSmallIntegerField(default=0)
    weekday = models.PositiveSmallIntegerField(
        default=0,
        help_text="0=lundi … 6=dimanche (hebdomadaire).",
    )
    # Rétention Restic forget
    keep_hourly = models.PositiveSmallIntegerField(default=0)
    keep_daily = models.PositiveSmallIntegerField(default=7)
    keep_weekly = models.PositiveSmallIntegerField(default=4)
    keep_monthly = models.PositiveSmallIntegerField(default=6)
    is_active = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("owner__username", "frequency")

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
        PRUNE = "prune", "Prune"
        FAIL = "fail", "Fail"
        DESTINATION = "destination", "Destination"

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
