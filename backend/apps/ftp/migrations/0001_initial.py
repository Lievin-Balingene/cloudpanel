from __future__ import annotations

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FtpAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("username", models.CharField(db_index=True, max_length=64, unique=True)),
                ("password_hash", models.CharField(max_length=256)),
                ("directory", models.CharField(help_text="Chemin absolu du home FTP (jail).", max_length=512)),
                (
                    "relative_directory",
                    models.CharField(
                        blank=True,
                        default="public_html",
                        help_text="Chemin relatif au home du compte propriétaire.",
                        max_length=512,
                    ),
                ),
                (
                    "quota_mb",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="0 = hérité / illimité selon package.",
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                (
                    "bandwidth_kbs",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Limite bande passante Ko/s (0 = illimitée).",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("is_suspended", models.BooleanField(default=False)),
                ("can_write", models.BooleanField(default=True)),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                ("last_login_at", models.DateTimeField(blank=True, null=True)),
                ("last_login_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ftp_accounts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("username",)},
        ),
        migrations.CreateModel(
            name="FtpLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("login", "Connexion"),
                            ("logout", "Déconnexion"),
                            ("login_failed", "Échec connexion"),
                            ("upload", "Upload"),
                            ("download", "Download"),
                            ("delete", "Suppression"),
                            ("mkdir", "Création dossier"),
                            ("rename", "Renommage"),
                            ("system", "Système"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("username", models.CharField(blank=True, default="", max_length=64)),
                ("path", models.CharField(blank=True, default="", max_length=1024)),
                ("bytes_transferred", models.BigIntegerField(default=0)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("message", models.TextField(blank=True, default="")),
                ("success", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                (
                    "account",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="logs",
                        to="ftp.ftpaccount",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ftp_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddIndex(
            model_name="ftpaccount",
            index=models.Index(fields=["owner", "is_active"], name="ftp_ftpacco_owner_i_0a1b2c_idx"),
        ),
        migrations.AddIndex(
            model_name="ftpaccount",
            index=models.Index(fields=["is_suspended"], name="ftp_ftpacco_is_susp_1d2e3f_idx"),
        ),
        migrations.AddIndex(
            model_name="ftplog",
            index=models.Index(fields=["username", "created_at"], name="ftp_ftplog_usernam_2a3b4c_idx"),
        ),
        migrations.AddIndex(
            model_name="ftplog",
            index=models.Index(fields=["event_type", "created_at"], name="ftp_ftplog_event_t_3b4c5d_idx"),
        ),
    ]
