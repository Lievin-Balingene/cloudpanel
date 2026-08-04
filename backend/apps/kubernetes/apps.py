from __future__ import annotations

from django.apps import AppConfig


class KubernetesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.kubernetes"
    label = "kubernetes"
    verbose_name = "Kubernetes"
