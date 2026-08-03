from __future__ import annotations

from django.contrib import admin

from apps.backups.models import BackupArchive, BackupEventLog, BackupSchedule


class BackupEventLogInline(admin.TabularInline):
    model = BackupEventLog
    extra = 0
    fk_name = "archive"
    readonly_fields = ("event_type", "success", "message", "created_at", "owner")


@admin.register(BackupArchive)
class BackupArchiveAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "backup_type", "status", "size_bytes", "completed_at")
    list_filter = ("status", "backup_type")
    search_fields = ("name", "owner__username", "file_name")
    inlines = [BackupEventLogInline]


@admin.register(BackupSchedule)
class BackupScheduleAdmin(admin.ModelAdmin):
    list_display = ("owner", "frequency", "hour", "weekday", "is_active", "last_run_at")
    list_filter = ("frequency", "is_active")
    search_fields = ("owner__username",)


@admin.register(BackupEventLog)
class BackupEventLogAdmin(admin.ModelAdmin):
    list_display = ("owner", "archive", "event_type", "success", "created_at")
    list_filter = ("event_type", "success")
