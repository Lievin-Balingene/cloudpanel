from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("dns", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Domain",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(db_index=True, max_length=255, unique=True)),
                (
                    "domain_type",
                    models.CharField(
                        choices=[
                            ("primary", "Domaine principal"),
                            ("addon", "Addon domain"),
                            ("subdomain", "Sous-domaine"),
                            ("parked", "Parked / Alias de domaine"),
                            ("alias", "Alias"),
                        ],
                        db_index=True,
                        default="primary",
                        max_length=16,
                    ),
                ),
                ("document_root", models.CharField(blank=True, default="", max_length=512)),
                ("is_active", models.BooleanField(default=True)),
                ("is_suspended", models.BooleanField(default=False)),
                ("create_dns_zone", models.BooleanField(default=True)),
                ("ipv4_address", models.GenericIPAddressField(blank=True, null=True, protocol="IPv4")),
                ("ipv6_address", models.GenericIPAddressField(blank=True, null=True, protocol="IPv6")),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "dns_zone",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="hosted_domains",
                        to="dns.dnszone",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="domains",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        help_text="Domaine parent pour sous-domaine / alias.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="children",
                        to="domains.domain",
                    ),
                ),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="DomainRedirect",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_path", models.CharField(default="/", max_length=512)),
                ("destination_url", models.URLField(max_length=2048)),
                (
                    "redirect_type",
                    models.CharField(
                        choices=[("301", "301 Permanent"), ("302", "302 Temporary")],
                        default="301",
                        max_length=3,
                    ),
                ),
                ("wildcard", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "domain",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="redirects",
                        to="domains.domain",
                    ),
                ),
            ],
            options={"ordering": ("domain_id", "source_path"), "unique_together": {("domain", "source_path")}},
        ),
        migrations.CreateModel(
            name="SslCertificate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "provider",
                    models.CharField(
                        choices=[("letsencrypt", "Let's Encrypt"), ("custom", "Personnalisé")],
                        default="letsencrypt",
                        max_length=32,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "En attente"),
                            ("issuing", "Émission"),
                            ("active", "Actif"),
                            ("expired", "Expiré"),
                            ("failed", "Échec"),
                            ("revoked", "Révoqué"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("common_name", models.CharField(blank=True, default="", max_length=255)),
                ("alt_names", models.JSONField(blank=True, default=list)),
                ("certificate_pem", models.TextField(blank=True, default="")),
                ("private_key_pem", models.TextField(blank=True, default="")),
                ("chain_pem", models.TextField(blank=True, default="")),
                ("auto_renew", models.BooleanField(default=True)),
                ("issued_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True, default="")),
                ("last_checked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "domain",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ssl",
                        to="domains.domain",
                    ),
                ),
            ],
            options={
                "verbose_name": "Certificat SSL",
                "verbose_name_plural": "Certificats SSL",
            },
        ),
        migrations.AddIndex(
            model_name="domain",
            index=models.Index(fields=["owner", "domain_type"], name="domains_dom_owner_i_0a1b2c_idx"),
        ),
    ]
