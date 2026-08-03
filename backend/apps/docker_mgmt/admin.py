from __future__ import annotations

from django.contrib import admin

from apps.docker_mgmt.models import DockerContainer, DockerContainerLog


class DockerContainerLogInline(admin.TabularInline):
    model = DockerContainerLog
    extra = 0
    readonly_fields = ("event_type", "success", "message", "created_at")


@admin.register(DockerContainer)
class DockerContainerAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "image", "tag", "status", "memory_mb", "is_active")
    list_filter = ("status", "restart_policy", "is_active")
    search_fields = ("name", "owner__username", "image", "container_id")
    inlines = [DockerContainerLogInline]


@admin.register(DockerContainerLog)
class DockerContainerLogAdmin(admin.ModelAdmin):
    list_display = ("container", "event_type", "success", "created_at")
    list_filter = ("event_type", "success")
