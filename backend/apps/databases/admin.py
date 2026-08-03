from __future__ import annotations

from django.contrib import admin

from apps.databases.models import Database, DatabasePrivilege, DatabaseUser


@admin.register(Database)
class DatabaseAdmin(admin.ModelAdmin):
    list_display = ("name", "engine", "owner", "is_active", "size_mb", "created_at")
    list_filter = ("engine", "is_active")
    search_fields = ("name", "owner__username")


@admin.register(DatabaseUser)
class DatabaseUserAdmin(admin.ModelAdmin):
    list_display = ("username", "engine", "host", "owner", "is_active")
    list_filter = ("engine", "is_active")
    search_fields = ("username", "owner__username")
    readonly_fields = ("password_hash",)


@admin.register(DatabasePrivilege)
class DatabasePrivilegeAdmin(admin.ModelAdmin):
    list_display = ("database", "user", "privileges", "created_at")
    list_filter = ("privileges",)
