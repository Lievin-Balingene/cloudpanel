from __future__ import annotations

from django.contrib import admin

from apps.node_apps.models import NodeApp


@admin.register(NodeApp)
class NodeAppAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "framework", "status", "port", "node_version", "is_active")
    list_filter = ("framework", "status", "is_active")
    search_fields = ("name", "owner__username", "domain_name")
