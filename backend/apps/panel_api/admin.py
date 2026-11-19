from django.contrib import admin

from apps.panel_api.models import ApiToken


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "audience", "token_prefix", "expires_at", "revoked_at", "last_used_at")
    search_fields = ("name", "user__username", "token_prefix")
    readonly_fields = ("token_hash", "token_prefix", "created_at", "last_used_at", "last_used_ip")
