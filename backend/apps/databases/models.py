"""Modèles bases de données d'hébergement."""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models


class DatabaseEngine(models.TextChoices):
    MYSQL = "mysql", "MySQL / MariaDB"
    POSTGRESQL = "postgresql", "PostgreSQL"


class Database(models.Model):
    """Base de données provisionnée pour un compte."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hosted_databases",
    )
    engine = models.CharField(max_length=16, choices=DatabaseEngine.choices, default=DatabaseEngine.MYSQL)
    name = models.CharField(max_length=64, db_index=True)
    charset = models.CharField(max_length=32, default="utf8mb4")
    collation = models.CharField(max_length=64, default="utf8mb4_unicode_ci")
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True, default="")
    size_mb = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        unique_together = ("engine", "name")
        indexes = [models.Index(fields=["owner", "engine"])]

    def __str__(self) -> str:
        return f"{self.engine}:{self.name}"


class DatabaseUser(models.Model):
    """Utilisateur SQL virtuel (préfixe compte)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="database_users",
    )
    engine = models.CharField(max_length=16, choices=DatabaseEngine.choices, default=DatabaseEngine.MYSQL)
    username = models.CharField(max_length=64, db_index=True)
    password_hash = models.CharField(max_length=256)
    # Mot de passe chiffré (Fernet) pour SSO phpMyAdmin style cPanel
    password_secret = models.TextField(blank=True, default="")
    host = models.CharField(max_length=64, default="localhost")
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("username",)
        unique_together = ("engine", "username", "host")
        indexes = [models.Index(fields=["owner", "engine"])]

    def __str__(self) -> str:
        return f"{self.username}@{self.host}"

    def set_password(self, raw: str) -> None:
        from apps.databases.crypto import encrypt_secret

        self.password_hash = make_password(raw)
        self.password_secret = encrypt_secret(raw)

    def check_password(self, raw: str) -> bool:
        return check_password(raw, self.password_hash)

    def get_password_plain(self) -> str | None:
        from apps.databases.crypto import decrypt_secret

        return decrypt_secret(self.password_secret)


class DatabasePrivilege(models.Model):
    """Attribution d'un utilisateur à une base."""

    database = models.ForeignKey(Database, on_delete=models.CASCADE, related_name="privileges")
    user = models.ForeignKey(DatabaseUser, on_delete=models.CASCADE, related_name="privileges")
    privileges = models.CharField(
        max_length=32,
        default="ALL",
        choices=(
            ("ALL", "Tous"),
            ("READ", "Lecture"),
            ("WRITE", "Écriture"),
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("database", "user")
        ordering = ("database__name", "user__username")

    def __str__(self) -> str:
        return f"{self.user.username} → {self.database.name} ({self.privileges})"
