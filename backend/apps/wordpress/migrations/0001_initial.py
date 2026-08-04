# Generated manually for WordPress sites
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("domains", "0001_initial"),
        ("databases", "0001_initial"),
        ("php", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="WordPressSite",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(default="Mon site", max_length=200)),
                ("admin_user", models.CharField(default="admin", max_length=60)),
                ("admin_email", models.EmailField(max_length=254)),
                ("document_root", models.CharField(max_length=512)),
                ("site_url", models.CharField(blank=True, default="", max_length=512)),
                ("admin_url", models.CharField(blank=True, default="", max_length=512)),
                ("php_version", models.CharField(blank=True, default="", max_length=16)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("provisioning", "Installation"),
                            ("active", "Actif"),
                            ("error", "Erreur"),
                            ("removing", "Suppression"),
                        ],
                        default="provisioning",
                        max_length=16,
                    ),
                ),
                ("last_error", models.TextField(blank=True, default="")),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "database",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="wordpress_sites",
                        to="databases.database",
                    ),
                ),
                (
                    "db_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="wordpress_sites",
                        to="databases.databaseuser",
                    ),
                ),
                (
                    "domain",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="wordpress_site",
                        to="domains.domain",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="wordpress_sites",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "php_selector",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="wordpress_sites",
                        to="php.phpselector",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="wordpresssite",
            index=models.Index(fields=["owner", "status"], name="wordpress_w_owner_i_7c2a1b_idx"),
        ),
    ]
