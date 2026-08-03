from __future__ import annotations

from django.contrib import admin

from apps.security.models import AccountLockout, IpAccessRule, LoginAttempt, SecurityPolicy


@admin.register(SecurityPolicy)
class SecurityPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "password_min_length",
        "ip_mode",
        "lockout_max_attempts",
        "force_2fa_admins",
        "updated_at",
    )


@admin.register(IpAccessRule)
class IpAccessRuleAdmin(admin.ModelAdmin):
    list_display = ("cidr", "list_type", "is_active", "created_at")
    list_filter = ("list_type", "is_active")


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("email", "ip_address", "success", "created_at")
    list_filter = ("success",)


@admin.register(AccountLockout)
class AccountLockoutAdmin(admin.ModelAdmin):
    list_display = ("key", "attempts", "locked_until", "updated_at")
    search_fields = ("key",)
