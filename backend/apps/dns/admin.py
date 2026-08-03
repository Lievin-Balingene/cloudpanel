from __future__ import annotations

from django.contrib import admin

from apps.dns.models import DnsRecord, DnsZone


class DnsRecordInline(admin.TabularInline):
    model = DnsRecord
    extra = 0


@admin.register(DnsZone)
class DnsZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "soa_serial", "dnssec_enabled", "is_active")
    search_fields = ("name", "owner__username")
    inlines = [DnsRecordInline]


@admin.register(DnsRecord)
class DnsRecordAdmin(admin.ModelAdmin):
    list_display = ("record_type", "name", "zone", "content", "ttl", "is_active")
    list_filter = ("record_type", "is_active")
