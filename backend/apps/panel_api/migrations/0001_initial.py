from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("accounts", "0009_remove_paid_until"),
    ]

    operations = [
        migrations.CreateModel(
            name="ApiToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("token_hash", models.CharField(db_index=True, max_length=64, unique=True)),
                ("token_prefix", models.CharField(max_length=16)),
                ("audience", models.CharField(choices=[("uapi", "Compte (UAPI)"), ("whm", "WHM"), ("both", "WHM et compte")], default="uapi", max_length=8)),
                ("scopes", models.JSONField(default=list)),
                ("ip_allowlist", models.TextField(blank=True, default="", help_text="IP ou CIDR séparés par des virgules. Vide = toutes les IP.")),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("last_used_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="api_tokens", to="accounts.user")),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddConstraint(
            model_name="apitoken",
            constraint=models.UniqueConstraint(fields=("user", "name"), name="panel_api_token_name_per_user"),
        ),
    ]
