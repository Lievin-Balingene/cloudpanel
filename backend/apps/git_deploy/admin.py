from __future__ import annotations

from django.contrib import admin

from apps.git_deploy.models import GitDeployLog, GitRepository


class GitDeployLogInline(admin.TabularInline):
    model = GitDeployLog
    extra = 0
    readonly_fields = ("event_type", "success", "message", "commit_hash", "created_at")


@admin.register(GitRepository)
class GitRepositoryAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "branch", "status", "auto_deploy", "last_deploy_at")
    list_filter = ("status", "auto_deploy", "is_active")
    search_fields = ("name", "owner__username", "remote_url")
    readonly_fields = ("webhook_token", "deploy_key_public", "deploy_key_private")
    inlines = [GitDeployLogInline]


@admin.register(GitDeployLog)
class GitDeployLogAdmin(admin.ModelAdmin):
    list_display = ("repository", "event_type", "success", "commit_hash", "created_at")
    list_filter = ("event_type", "success")
