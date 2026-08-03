from __future__ import annotations

from django.contrib import admin

from apps.ftp.models import FtpAccount, FtpLog


@admin.register(FtpAccount)
class FtpAccountAdmin(admin.ModelAdmin):
    list_display = (
        "username",
        "owner",
        "relative_directory",
        "is_active",
        "is_suspended",
        "last_login_at",
    )
    list_filter = ("is_active", "is_suspended", "can_write")
    search_fields = ("username", "owner__username", "directory")
    readonly_fields = ("password_hash", "directory", "last_login_at", "last_login_ip")


@admin.register(FtpLog)
class FtpLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "event_type",
        "username",
        "ip_address",
        "success",
        "bytes_transferred",
    )
    list_filter = ("event_type", "success")
    search_fields = ("username", "path", "message", "ip_address")
    readonly_fields = [f.name for f in FtpLog._meta.fields]
