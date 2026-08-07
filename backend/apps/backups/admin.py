from __future__ import annotations

from django.contrib import admin

from apps.backups.models import BackupArchive, BackupDestination, BackupEventLog, BackupSchedule


class BackupEventLogInline(admin.TabularInline):
    model = BackupEventLog
    extra = 0
    fk_name = "archive"
    readonly_fields = ("event_type", "success", "message", "created_at", "owner")


@admin.register(BackupDestination)
class BackupDestinationAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "owner", "is_default", "is_active", "updated_at")
    list_filter = ("provider", "is_active", "is_default")
    search_fields = ("name", "owner__username", "repository_uri")


@admin.register(BackupArchive)
class BackupArchiveAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "owner",
        "backup_type",
        "status",
        "progress",
        "size_bytes",
        "duration_seconds",
        "completed_at",
    )
    list_filter = ("status", "backup_type", "trigger")
    search_fields = ("name", "owner__username", "snapshot_id")
    inlines = [BackupEventLogInline]


@admin.register(BackupSchedule)
class BackupScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "owner",
        "name",
        "frequency",
        "hour",
        "is_active",
        "keep_daily",
        "last_run_at",
        "next_run_at",
    )
    list_filter = ("frequency", "is_active")
    search_fields = ("owner__username", "name")


@admin.register(BackupEventLog)
class BackupEventLogAdmin(admin.ModelAdmin):
    list_display = ("owner", "archive", "event_type", "success", "created_at")
    list_filter = ("event_type", "success")
