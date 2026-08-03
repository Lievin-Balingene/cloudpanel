"""Modèles PHP multi-version."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class PhpVersion(models.Model):
    """Version PHP installée / disponible sur le serveur."""

    version = models.CharField(max_length=16, unique=True, db_index=True)
    binary_path = models.CharField(max_length=512, blank=True, default="")
    fpm_socket = models.CharField(max_length=512, blank=True, default="")
    is_available = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-version",)

    def __str__(self) -> str:
        return f"PHP {self.version}"

    def save(self, *args, **kwargs) -> None:
        if self.is_default:
            PhpVersion.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class PhpSelector(models.Model):
    """Association version PHP ↔ chemin / domaine d'un compte."""

    class Handler(models.TextChoices):
        FPM = "fpm", "PHP-FPM"
        CGI = "cgi", "CGI"
        LSAPI = "lsapi", "LSAPI"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="php_selectors",
    )
    php_version = models.ForeignKey(
        PhpVersion,
        on_delete=models.PROTECT,
        related_name="selectors",
    )
    relative_path = models.CharField(
        max_length=255,
        default="public_html",
        help_text="Chemin relatif au home (ex: public_html ou domains/exemple.com).",
    )
    domain_name = models.CharField(max_length=255, blank=True, default="")
    handler = models.CharField(max_length=16, choices=Handler.choices, default=Handler.FPM)
    ini_settings = models.JSONField(
        default=dict,
        blank=True,
        help_text="Surcharges php.ini (memory_limit, display_errors…).",
    )
    extensions = models.JSONField(
        default=list,
        blank=True,
        help_text="Extensions activées (liste de noms).",
    )
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("relative_path",)
        unique_together = ("owner", "relative_path")
        indexes = [models.Index(fields=["owner", "is_active"])]

    def __str__(self) -> str:
        return f"{self.owner.username}:{self.relative_path} → {self.php_version.version}"
