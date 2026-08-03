from __future__ import annotations

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
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("create", "Création"),
                            ("update", "Modification"),
                            ("delete", "Suppression"),
                            ("login", "Connexion"),
                            ("logout", "Déconnexion"),
                            ("suspend", "Suspension"),
                            ("restore", "Restauration"),
                            ("system", "Système"),
                        ],
                        max_length=32,
                    ),
                ),
                ("resource_type", models.CharField(max_length=64)),
                ("resource_id", models.CharField(blank=True, default="", max_length=64)),
                ("message", models.TextField(blank=True, default="")),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, default="", max_length=512)),
                ("request_id", models.CharField(blank=True, default="", max_length=64)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["resource_type", "resource_id"], name="core_auditl_resourc_0a1b2c_idx"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["action", "created_at"], name="core_auditl_action_1d2e3f_idx"),
        ),
    ]
