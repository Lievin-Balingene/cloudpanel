from __future__ import annotations

from django.contrib import admin

from apps.packages.models import HostingPackage, PackageAssignment


@admin.register(HostingPackage)
class HostingPackageAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "package_type",
        "disk_mb",
        "domains",
        "is_active",
        "is_default",
        "owner",
    )
    list_filter = ("package_type", "is_active", "is_default")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(PackageAssignment)
class PackageAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "package", "assigned_at", "assigned_by")
    search_fields = ("user__username", "package__name")
