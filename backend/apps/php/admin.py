from __future__ import annotations

from django.contrib import admin

from apps.php.models import PhpSelector, PhpVersion


@admin.register(PhpVersion)
class PhpVersionAdmin(admin.ModelAdmin):
    list_display = ("version", "is_available", "is_default", "binary_path")
    list_filter = ("is_available", "is_default")


@admin.register(PhpSelector)
class PhpSelectorAdmin(admin.ModelAdmin):
    list_display = ("owner", "relative_path", "php_version", "handler", "domain_name", "is_active")
    list_filter = ("handler", "is_active")
    search_fields = ("owner__username", "relative_path", "domain_name")
