from __future__ import annotations

from django.apps import AppConfig


class FtpConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ftp"
    label = "ftp"
    verbose_name = "FTP"
