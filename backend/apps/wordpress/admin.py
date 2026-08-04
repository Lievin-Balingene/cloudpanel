from __future__ import annotations

from django.contrib import admin

from apps.wordpress.models import WordPressSite


@admin.register(WordPressSite)
class WordPressSiteAdmin(admin.ModelAdmin):
    list_display = ("domain", "owner", "title", "status", "php_version", "created_at")
    list_filter = ("status",)
    search_fields = ("domain__name", "owner__username", "title")
    raw_id_fields = ("owner", "domain", "database", "db_user", "php_selector")
