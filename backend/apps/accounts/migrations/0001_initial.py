# Generated manually for initial release — run makemigrations on target if needed.
from __future__ import annotations

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

import apps.accounts.managers


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="User",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text="Designates that this user has all permissions without explicitly assigning them.",
                        verbose_name="superuser status",
                    ),
                ),
                ("email", models.EmailField(db_index=True, max_length=254, unique=True)),
                ("username", models.CharField(db_index=True, max_length=150, unique=True)),
                ("first_name", models.CharField(blank=True, default="", max_length=150)),
                ("last_name", models.CharField(blank=True, default="", max_length=150)),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("administrator", "Administrateur"),
                            ("reseller", "Revendeur"),
                            ("client", "Client"),
                        ],
                        db_index=True,
                        default="client",
                        max_length=32,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("is_staff", models.BooleanField(default=False)),
                ("is_suspended", models.BooleanField(default=False)),
                ("must_change_password", models.BooleanField(default=False)),
                ("two_factor_enabled", models.BooleanField(default=False)),
                ("two_factor_secret", models.CharField(blank=True, default="", max_length=64)),
                (
                    "module_permissions",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Liste de codes de permissions module (ex: domains.manage).",
                    ),
                ),
                (
                    "system_username",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Nom d'utilisateur système Linux associé (si provisionné).",
                        max_length=32,
                    ),
                ),
                ("home_directory", models.CharField(blank=True, default="", max_length=512)),
                ("last_login_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("date_joined", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        help_text="The groups this user belongs to.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        help_text="Revendeur parent pour un client, ou admin pour un revendeur.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="children",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this user.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
            options={
                "ordering": ("username",),
            },
            managers=[
                ("objects", apps.accounts.managers.UserManager()),
            ],
        ),
        migrations.CreateModel(
            name="ResourceQuota",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "disk_mb",
                    models.PositiveIntegerField(
                        default=10240, validators=[django.core.validators.MinValueValidator(0)]
                    ),
                ),
                (
                    "cpu_millicores",
                    models.PositiveIntegerField(
                        default=1000, validators=[django.core.validators.MinValueValidator(0)]
                    ),
                ),
                (
                    "ram_mb",
                    models.PositiveIntegerField(
                        default=1024, validators=[django.core.validators.MinValueValidator(0)]
                    ),
                ),
                ("emails", models.PositiveIntegerField(default=10)),
                ("databases", models.PositiveIntegerField(default=5)),
                ("domains", models.PositiveIntegerField(default=5)),
                ("ftp_accounts", models.PositiveIntegerField(default=5)),
                ("python_apps", models.PositiveIntegerField(default=2)),
                ("node_apps", models.PositiveIntegerField(default=2)),
                ("docker_containers", models.PositiveIntegerField(default=0)),
                ("unlimited_disk", models.BooleanField(default=False)),
                ("unlimited_cpu", models.BooleanField(default=False)),
                ("unlimited_ram", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="quota",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Quota",
                "verbose_name_plural": "Quotas",
            },
        ),
        migrations.CreateModel(
            name="UserSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("jti", models.CharField(db_index=True, max_length=64, unique=True)),
                ("user_agent", models.CharField(blank=True, default="", max_length=512)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("expires_at", models.DateTimeField()),
                ("is_revoked", models.BooleanField(default=False)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-last_seen_at",),
            },
        ),
        migrations.AddIndex(
            model_name="user",
            index=models.Index(fields=["role", "is_active"], name="accounts_us_role_7a0e3a_idx"),
        ),
        migrations.AddIndex(
            model_name="user",
            index=models.Index(fields=["parent", "role"], name="accounts_us_parent__7f2c1a_idx"),
        ),
    ]
