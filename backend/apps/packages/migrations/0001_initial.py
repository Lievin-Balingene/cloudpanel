# Generated manually for packages module
from __future__ import annotations

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="HostingPackage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("slug", models.SlugField(blank=True, max_length=140, unique=True)),
                ("description", models.TextField(blank=True, default="")),
                (
                    "package_type",
                    models.CharField(
                        choices=[("client", "Compte client"), ("reseller", "Compte revendeur")],
                        db_index=True,
                        default="client",
                        max_length=16,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("is_default", models.BooleanField(default=False, help_text="Package par défaut lors de la création d'un compte.")),
                ("disk_mb", models.PositiveIntegerField(default=10240, validators=[django.core.validators.MinValueValidator(0)])),
                ("bandwidth_mb", models.PositiveIntegerField(default=102400, help_text="Quota mensuel de bande passante en Mo (0 = illimité si unlimited_bandwidth).", validators=[django.core.validators.MinValueValidator(0)])),
                ("unlimited_disk", models.BooleanField(default=False)),
                ("unlimited_bandwidth", models.BooleanField(default=False)),
                ("cpu_millicores", models.PositiveIntegerField(default=1000)),
                ("ram_mb", models.PositiveIntegerField(default=1024)),
                ("unlimited_cpu", models.BooleanField(default=False)),
                ("unlimited_ram", models.BooleanField(default=False)),
                ("inode_limit", models.PositiveIntegerField(default=200000)),
                ("max_processes", models.PositiveIntegerField(default=100)),
                ("max_nproc", models.PositiveIntegerField(default=40)),
                ("max_entry_processes", models.PositiveIntegerField(default=20)),
                ("domains", models.PositiveIntegerField(default=1)),
                ("subdomains", models.PositiveIntegerField(default=5)),
                ("parked_domains", models.PositiveIntegerField(default=5)),
                ("addon_domains", models.PositiveIntegerField(default=0)),
                ("emails", models.PositiveIntegerField(default=10)),
                ("email_lists", models.PositiveIntegerField(default=2)),
                ("databases", models.PositiveIntegerField(default=5)),
                ("ftp_accounts", models.PositiveIntegerField(default=5)),
                ("python_apps", models.PositiveIntegerField(default=1)),
                ("node_apps", models.PositiveIntegerField(default=1)),
                ("docker_containers", models.PositiveIntegerField(default=0)),
                ("cron_jobs", models.PositiveIntegerField(default=10)),
                ("max_accounts", models.PositiveIntegerField(default=0, help_text="Nombre max de comptes clients (revendeur). 0 = illimité.")),
                ("can_create_packages", models.BooleanField(default=False)),
                ("allow_ssh", models.BooleanField(default=False)),
                ("allow_dns", models.BooleanField(default=True)),
                ("allow_ssl", models.BooleanField(default=True)),
                ("allow_backup", models.BooleanField(default=True)),
                ("allow_git", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(blank=True, help_text="Null = package système WHM. Sinon package créé par un revendeur.", null=True, on_delete=django.db.models.deletion.CASCADE, related_name="owned_packages", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("sort_order", "name")},
        ),
        migrations.CreateModel(
            name="PackageAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("assigned_at", models.DateTimeField(auto_now=True)),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                ("assigned_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="package_assignments_made", to=settings.AUTH_USER_MODEL)),
                ("package", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="assignments", to="packages.hostingpackage")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="package_assignment", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Assignation de package",
                "verbose_name_plural": "Assignations de packages",
            },
        ),
        migrations.AddIndex(
            model_name="hostingpackage",
            index=models.Index(fields=["package_type", "is_active"], name="packages_ho_package_0a1b2c_idx"),
        ),
    ]
