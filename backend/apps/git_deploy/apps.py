from __future__ import annotations

from django.apps import AppConfig


class GitDeployConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.git_deploy"
    label = "git_deploy"
    verbose_name = "Git Deploy"
