from __future__ import annotations

from django.contrib import admin

from apps.core.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "resource_type", "resource_id", "actor")
    list_filter = ("action", "resource_type")
    search_fields = ("message", "resource_id", "request_id")
    readonly_fields = (
        "actor",
        "action",
        "resource_type",
        "resource_id",
        "message",
        "ip_address",
        "user_agent",
        "request_id",
        "metadata",
        "created_at",
    )
