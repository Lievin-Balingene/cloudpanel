from __future__ import annotations

from django.contrib import admin

from apps.domains.models import Domain, DomainRedirect, SslCertificate


class DomainRedirectInline(admin.TabularInline):
    model = DomainRedirect
    extra = 0


class SslCertificateInline(admin.StackedInline):
    model = SslCertificate
    extra = 0
    readonly_fields = (
        "status",
        "issued_at",
        "expires_at",
        "last_error",
        "last_checked_at",
    )


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ("name", "domain_type", "owner", "is_active", "is_suspended", "dns_zone")
    list_filter = ("domain_type", "is_active", "is_suspended")
    search_fields = ("name", "owner__username")
    inlines = [DomainRedirectInline, SslCertificateInline]


@admin.register(SslCertificate)
class SslCertificateAdmin(admin.ModelAdmin):
    list_display = ("domain", "provider", "status", "expires_at", "auto_renew")
    list_filter = ("provider", "status", "auto_renew")
    search_fields = ("domain__name", "common_name")
