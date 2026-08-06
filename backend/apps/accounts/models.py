"""Modèles utilisateurs, quotas et permissions granulaires."""
from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.accounts.managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """Utilisateur V-zone avec rôle et quotas associés."""

    class Role(models.TextChoices):
        ADMINISTRATOR = "administrator", "Administrateur"
        RESELLER = "reseller", "Revendeur"
        CLIENT = "client", "Client"

    email = models.EmailField(unique=True, db_index=True)
    username = models.CharField(max_length=150, unique=True, db_index=True)
    first_name = models.CharField(max_length=150, blank=True, default="")
    last_name = models.CharField(max_length=150, blank=True, default="")
    role = models.CharField(
        max_length=32,
        choices=Role.choices,
        default=Role.CLIENT,
        db_index=True,
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_suspended = models.BooleanField(default=False)
    must_change_password = models.BooleanField(default=False)
    two_factor_enabled = models.BooleanField(default=False)
    two_factor_secret = models.CharField(max_length=255, blank=True, default="")
    module_permissions = models.JSONField(
        default=list,
        blank=True,
        help_text="Liste de codes de permissions module (ex: domains.manage).",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        help_text="Revendeur parent pour un client, ou admin pour un revendeur.",
    )
    system_username = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Nom d'utilisateur système Linux associé (si provisionné).",
    )
    home_directory = models.CharField(max_length=512, blank=True, default="")
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    date_joined = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        ordering = ("username",)
        indexes = [
            models.Index(fields=["role", "is_active"]),
            models.Index(fields=["parent", "role"]),
        ]

    def __str__(self) -> str:
        return f"{self.username} ({self.role})"

    @property
    def is_administrator(self) -> bool:
        return self.role == self.Role.ADMINISTRATOR

    @property
    def is_reseller(self) -> bool:
        return self.role == self.Role.RESELLER

    @property
    def is_client(self) -> bool:
        return self.role == self.Role.CLIENT

    def has_module_perm(self, codename: str) -> bool:
        if self.is_administrator:
            return True
        return codename in (self.module_permissions or [])


class ResourceQuota(models.Model):
    """Quotas de ressources attachés à un utilisateur."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="quota",
    )
    # Unités : Mo pour disque, millicores pour CPU, Mo pour RAM
    disk_mb = models.PositiveIntegerField(default=10240, validators=[MinValueValidator(0)])
    cpu_millicores = models.PositiveIntegerField(default=1000, validators=[MinValueValidator(0)])
    ram_mb = models.PositiveIntegerField(default=1024, validators=[MinValueValidator(0)])
    emails = models.PositiveIntegerField(default=10)
    databases = models.PositiveIntegerField(default=5)
    domains = models.PositiveIntegerField(default=5)
    ftp_accounts = models.PositiveIntegerField(default=5)
    python_apps = models.PositiveIntegerField(default=2)
    node_apps = models.PositiveIntegerField(default=2)
    docker_containers = models.PositiveIntegerField(default=0)
    # 0 = illimité pour les compteurs d'usage
    unlimited_disk = models.BooleanField(default=False)
    unlimited_cpu = models.BooleanField(default=False)
    unlimited_ram = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Quota"
        verbose_name_plural = "Quotas"

    def __str__(self) -> str:
        return f"Quota({self.user.username})"

    def as_dict(self) -> dict:
        return {
            "disk_mb": None if self.unlimited_disk else self.disk_mb,
            "cpu_millicores": None if self.unlimited_cpu else self.cpu_millicores,
            "ram_mb": None if self.unlimited_ram else self.ram_mb,
            "emails": self.emails,
            "databases": self.databases,
            "domains": self.domains,
            "ftp_accounts": self.ftp_accounts,
            "python_apps": self.python_apps,
            "node_apps": self.node_apps,
            "docker_containers": self.docker_containers,
        }


class UserSession(models.Model):
    """Session active suivie côté API (complète JWT)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    jti = models.CharField(max_length=64, unique=True, db_index=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    is_revoked = models.BooleanField(default=False)

    class Meta:
        ordering = ("-last_seen_at",)

    def __str__(self) -> str:
        return f"Session({self.user_id}, {self.jti[:8]})"
