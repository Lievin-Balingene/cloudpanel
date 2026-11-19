from django.contrib import admin

from apps.local_context.models import LocalSiteProfile


@admin.register(LocalSiteProfile)
class LocalSiteProfileAdmin(admin.ModelAdmin):
    list_display = ("country", "timezone", "data_saver", "lite_panel", "require_phone")
