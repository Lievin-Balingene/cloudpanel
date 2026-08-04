"""Modèles sites WordPress."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class WordPressSite(models.Model):
    class Status(models.TextChoices):
        PROVISIONING = "provisioning", "Installation"
        ACTIVE = "active", "Actif"
        ERROR = "error", "Erreur"
        REMOVING = "removing", "Suppression"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wordpress_sites",
    )
    domain = models.OneToOneField(
        "domains.Domain",
        on_delete=models.CASCADE,
        related_name="wordpress_site",
    )
    title = models.CharField(max_length=200, default="Mon site")
    admin_user = models.CharField(max_length=60, default="admin")
    admin_email = models.EmailField()
    document_root = models.CharField(max_length=512)
    site_url = models.CharField(max_length=512, blank=True, default="")
    admin_url = models.CharField(max_length=512, blank=True, default="")
    database = models.ForeignKey(
        "databases.Database",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wordpress_sites",
    )
    db_user = models.ForeignKey(
        "databases.DatabaseUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wordpress_sites",
    )
    php_selector = models.ForeignKey(
        "php.PhpSelector",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wordpress_sites",
    )
    php_version = models.CharField(max_length=16, blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PROVISIONING,
    )
    last_error = models.TextField(blank=True, default="")
    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["owner", "status"])]

    def __str__(self) -> str:
        return f"WP:{self.domain.name}"
