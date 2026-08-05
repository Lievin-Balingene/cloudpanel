from django.contrib import admin

from apps.cron.models import CronJob


@admin.register(CronJob)
class CronJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "owner",
        "schedule_line",
        "command",
        "is_active",
        "common",
        "updated_at",
    )
    list_filter = ("is_active", "common")
    search_fields = ("command", "label", "owner__username", "email_to")
