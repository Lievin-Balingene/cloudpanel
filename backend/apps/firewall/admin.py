from __future__ import annotations

from django.contrib import admin

from apps.firewall.models import Fail2BanBan, Fail2BanJail, FirewallEventLog, FirewallRule


@admin.register(FirewallRule)
class FirewallRuleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "action",
        "protocol",
        "direction",
        "port_start",
        "is_enabled",
        "is_applied",
        "priority",
    )
    list_filter = ("action", "protocol", "is_enabled", "is_applied")
    search_fields = ("name", "source_cidr", "dest_cidr")


@admin.register(Fail2BanJail)
class Fail2BanJailAdmin(admin.ModelAdmin):
    list_display = ("name", "is_enabled", "currently_banned", "total_banned", "max_retry")
    list_filter = ("is_enabled",)
    search_fields = ("name", "filter_name")


@admin.register(Fail2BanBan)
class Fail2BanBanAdmin(admin.ModelAdmin):
    list_display = ("ip_address", "jail", "status", "banned_at", "unbanned_at")
    list_filter = ("status", "jail")
    search_fields = ("ip_address",)


@admin.register(FirewallEventLog)
class FirewallEventLogAdmin(admin.ModelAdmin):
    list_display = ("event_type", "success", "actor", "created_at")
    list_filter = ("event_type", "success")
