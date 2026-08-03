"""Modèles de packages d'hébergement inspirés des plans WHM."""
from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify


class HostingPackage(models.Model):
    """Plan de ressources applicable à un compte client ou revendeur."""

    class PackageType(models.TextChoices):
        CLIENT = "client", "Compte client"
        RESELLER = "reseller", "Compte revendeur"

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True, default="")
    package_type = models.CharField(
        max_length=16,
        choices=PackageType.choices,
        default=PackageType.CLIENT,
        db_index=True,
    )
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        help_text="Package par défaut lors de la création d'un compte.",
    )

    # Limites stockage / bande passante
    disk_mb = models.PositiveIntegerField(default=10240, validators=[MinValueValidator(0)])
    bandwidth_mb = models.PositiveIntegerField(
        default=102400,
        validators=[MinValueValidator(0)],
        help_text="Quota mensuel de bande passante en Mo (0 = illimité si unlimited_bandwidth).",
    )
    unlimited_disk = models.BooleanField(default=False)
    unlimited_bandwidth = models.BooleanField(default=False)

    # Limites CPU / RAM (contrôle serveur)
    cpu_millicores = models.PositiveIntegerField(default=1000)
    ram_mb = models.PositiveIntegerField(default=1024)
    unlimited_cpu = models.BooleanField(default=False)
    unlimited_ram = models.BooleanField(default=False)
    inode_limit = models.PositiveIntegerField(default=200000)
    max_processes = models.PositiveIntegerField(default=100)
    max_nproc = models.PositiveIntegerField(default=40)
    max_entry_processes = models.PositiveIntegerField(default=20)

    # Compteurs services
    domains = models.PositiveIntegerField(default=1)
    subdomains = models.PositiveIntegerField(default=5)
    parked_domains = models.PositiveIntegerField(default=5)
    addon_domains = models.PositiveIntegerField(default=0)
    emails = models.PositiveIntegerField(default=10)
    email_lists = models.PositiveIntegerField(default=2)
    databases = models.PositiveIntegerField(default=5)
    ftp_accounts = models.PositiveIntegerField(default=5)
    python_apps = models.PositiveIntegerField(default=1)
    node_apps = models.PositiveIntegerField(default=1)
    docker_containers = models.PositiveIntegerField(default=0)
    cron_jobs = models.PositiveIntegerField(default=10)

    # Spécifique revendeur
    max_accounts = models.PositiveIntegerField(
        default=0,
        help_text="Nombre max de comptes clients (revendeur). 0 = illimité.",
    )
    can_create_packages = models.BooleanField(default=False)

    # Features booléennes
    allow_ssh = models.BooleanField(default=False)
    allow_dns = models.BooleanField(default=True)
    allow_ssl = models.BooleanField(default=True)
    allow_backup = models.BooleanField(default=True)
    allow_git = models.BooleanField(default=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="owned_packages",
        help_text="Null = package système WHM. Sinon package créé par un revendeur.",
    )
    sort_order = models.PositiveIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "name")
        indexes = [
            models.Index(fields=["package_type", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.package_type})"

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            base = slugify(self.name) or "package"
            slug = base
            n = 1
            while HostingPackage.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        if self.is_default:
            HostingPackage.objects.filter(
                package_type=self.package_type,
                is_default=True,
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    def quota_payload(self) -> dict:
        return {
            "disk_mb": self.disk_mb,
            "cpu_millicores": self.cpu_millicores,
            "ram_mb": self.ram_mb,
            "emails": self.emails,
            "databases": self.databases,
            "domains": self.domains,
            "ftp_accounts": self.ftp_accounts,
            "python_apps": self.python_apps,
            "node_apps": self.node_apps,
            "docker_containers": self.docker_containers,
            "unlimited_disk": self.unlimited_disk,
            "unlimited_cpu": self.unlimited_cpu,
            "unlimited_ram": self.unlimited_ram,
        }


class PackageAssignment(models.Model):
    """Liaison compte ↔ package avec horodatage."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="package_assignment",
    )
    package = models.ForeignKey(
        HostingPackage,
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="package_assignments_made",
    )
    assigned_at = models.DateTimeField(auto_now=True)
    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        verbose_name = "Assignation de package"
        verbose_name_plural = "Assignations de packages"

    def __str__(self) -> str:
        return f"{self.user.username} → {self.package.name}"
