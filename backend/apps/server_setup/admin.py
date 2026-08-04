from django.contrib import admin

from apps.server_setup.models import ServerSetup


@admin.register(ServerSetup)
class ServerSetupAdmin(admin.ModelAdmin):
    list_display = ("hostname", "nameserver1", "nameserver2", "updated_at")
