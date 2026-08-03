from __future__ import annotations

from django.contrib import admin

from apps.monitoring.models import AlertEvent, AlertRule


class AlertEventInline(admin.TabularInline):
    model = AlertEvent
    extra = 0
    readonly_fields = (
        "status",
        "metric_value",
        "message",
        "notified",
        "notified_at",
        "created_at",
    )


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "metric",
        "operator",
        "threshold",
        "severity",
        "is_active",
        "last_triggered_at",
    )
    list_filter = ("metric", "severity", "is_active")
    search_fields = ("name", "service_name", "recipients")
    inlines = [AlertEventInline]


@admin.register(AlertEvent)
class AlertEventAdmin(admin.ModelAdmin):
    list_display = ("rule", "status", "metric_value", "notified", "created_at")
    list_filter = ("status", "notified")
    search_fields = ("rule__name", "message")
