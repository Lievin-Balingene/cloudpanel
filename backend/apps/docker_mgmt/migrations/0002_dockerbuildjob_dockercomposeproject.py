# Generated manually for Docker build/compose panel
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("docker_mgmt", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="DockerBuildJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(db_index=True, max_length=64)),
                (
                    "context_path",
                    models.CharField(help_text="Dossier relatif au home (contexte docker build).", max_length=512),
                ),
                ("dockerfile", models.CharField(default="Dockerfile", max_length=255)),
                ("image_name", models.CharField(help_text="Nom local sans préfixe utilisateur.", max_length=120)),
                ("tag", models.CharField(default="latest", max_length=64)),
                ("built_image_ref", models.CharField(blank=True, default="", max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "En attente"),
                            ("running", "Build en cours"),
                            ("completed", "Terminé"),
                            ("failed", "Échec"),
                            ("cancelled", "Annulé"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("progress", models.PositiveSmallIntegerField(default=0)),
                ("log", models.TextField(blank=True, default="")),
                ("last_error", models.TextField(blank=True, default="")),
                ("celery_task_id", models.CharField(blank=True, default="", max_length=64)),
                ("no_cache", models.BooleanField(default=False)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="docker_build_jobs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
                "unique_together": {("owner", "name")},
            },
        ),
        migrations.CreateModel(
            name="DockerComposeProject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(db_index=True, max_length=64)),
                (
                    "project_path",
                    models.CharField(help_text="Dossier relatif contenant le fichier compose.", max_length=512),
                ),
                ("compose_file", models.CharField(default="docker-compose.yml", max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("created", "Créé"),
                            ("running", "En cours"),
                            ("stopped", "Arrêté"),
                            ("error", "Erreur"),
                        ],
                        default="created",
                        max_length=16,
                    ),
                ),
                ("log", models.TextField(blank=True, default="")),
                ("last_error", models.TextField(blank=True, default="")),
                ("celery_task_id", models.CharField(blank=True, default="", max_length=64)),
                ("last_deployed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="docker_compose_projects",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("name",),
                "unique_together": {("owner", "name")},
            },
        ),
        migrations.AddIndex(
            model_name="dockerbuildjob",
            index=models.Index(fields=["owner", "status"], name="docker_mgm_owner_i_build_idx"),
        ),
        migrations.AddIndex(
            model_name="dockercomposeproject",
            index=models.Index(fields=["owner", "status"], name="docker_mgm_owner_i_comp_idx"),
        ),
    ]
