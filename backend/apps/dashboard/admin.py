from __future__ import annotations

from django.contrib import admin

from apps.dashboard.models import ResourceSnapshot


@admin.register(ResourceSnapshot)
class ResourceSnapshotAdmin(admin.ModelAdmin):
    list_display = ("collected_at", "cpu_percent", "ram_percent", "disk_percent", "load_1")
    readonly_fields = [f.name for f in ResourceSnapshot._meta.fields]
