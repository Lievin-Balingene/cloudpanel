from __future__ import annotations

from django.contrib import admin

from apps.python_apps.models import PythonApp


@admin.register(PythonApp)
class PythonAppAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "mode", "framework", "status", "port", "is_active")
    list_filter = ("mode", "framework", "status", "is_active")
    search_fields = ("name", "owner__username", "domain_name")
