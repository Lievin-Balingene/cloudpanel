from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.accounts.models import ResourceQuota, User, UserSession


class ResourceQuotaInline(admin.StackedInline):
    model = ResourceQuota
    can_delete = False


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("username",)
    list_display = ("username", "email", "role", "is_active", "is_suspended", "date_joined")
    list_filter = ("role", "is_active", "is_suspended", "two_factor_enabled")
    search_fields = ("username", "email", "first_name", "last_name")
    inlines = [ResourceQuotaInline]
    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        ("Profil", {"fields": ("first_name", "last_name", "role", "parent")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "is_suspended",
                    "must_change_password",
                    "module_permissions",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("2FA", {"fields": ("two_factor_enabled", "two_factor_secret")}),
        ("Système", {"fields": ("system_username", "home_directory", "last_login_ip")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "username", "password1", "password2", "role"),
            },
        ),
    )
    filter_horizontal = ("groups", "user_permissions")


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "jti", "ip_address", "created_at", "is_revoked")
    list_filter = ("is_revoked",)
    search_fields = ("jti", "user__username", "ip_address")
