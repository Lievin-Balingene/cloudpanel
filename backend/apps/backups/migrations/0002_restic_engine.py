# Generated manually for Restic/Rclone engine

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("backups", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BackupDestination",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=64)),
                ("label", models.CharField(blank=True, default="", max_length=120)),
                (
                    "provider",
                    models.CharField(
                        choices=[
                            ("local", "Local"),
                            ("sftp", "SFTP"),
                            ("s3", "Amazon S3 compatible"),
                            ("b2", "Backblaze B2"),
                            ("r2", "Cloudflare R2"),
                            ("gdrive", "Google Drive"),
                        ],
                        default="local",
                        max_length=16,
                    ),
                ),
                ("config", models.JSONField(blank=True, default=dict)),
                ("restic_password_secret", models.TextField(blank=True, default="")),
                ("credentials_secret", models.TextField(blank=True, default="")),
                ("rclone_remote", models.CharField(blank=True, default="", max_length=64)),
                ("repository_uri", models.CharField(blank=True, default="", help_text="URI Restic, ex. /path ou rclone:remote:bucket/path", max_length=512)),
                ("is_default", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("last_error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        help_text="Null = destination globale admin.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="backup_destinations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("name",),
                "indexes": [models.Index(fields=["provider", "is_active"], name="backups_bac_provide_7a0c1a_idx")],
                "unique_together": {("owner", "name")},
            },
        ),
        migrations.AddField(
            model_name="backuparchive",
            name="celery_task_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="backuparchive",
            name="duration_seconds",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="backuparchive",
            name="files_changed",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="backuparchive",
            name="files_new",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="backuparchive",
            name="files_unmodified",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="backuparchive",
            name="log",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="backuparchive",
            name="parent_snapshot_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="backuparchive",
            name="progress",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="backuparchive",
            name="snapshot_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="backuparchive",
            name="started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="backuparchive",
            name="trigger",
            field=models.CharField(
                choices=[("manual", "Manuel"), ("scheduled", "Planifié"), ("api", "API")],
                default="manual",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="backuparchive",
            name="backup_type",
            field=models.CharField(
                choices=[
                    ("full", "Complète"),
                    ("incremental", "Incrémentale"),
                    ("home", "Fichiers"),
                    ("databases", "Bases"),
                    ("email", "Email"),
                    ("custom", "Personnalisée"),
                ],
                default="full",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="backuparchive",
            name="destination",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="archives",
                to="backups.backupdestination",
            ),
        ),
        migrations.AddIndex(
            model_name="backuparchive",
            index=models.Index(fields=["snapshot_id"], name="backups_bac_snapsho_9f3a2b_idx"),
        ),
        migrations.AlterField(
            model_name="backupeventlog",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("create", "Create"),
                    ("complete", "Complete"),
                    ("restore", "Restore"),
                    ("delete", "Delete"),
                    ("download", "Download"),
                    ("schedule", "Schedule"),
                    ("prune", "Prune"),
                    ("fail", "Fail"),
                    ("destination", "Destination"),
                ],
                max_length=16,
            ),
        ),
        # BackupSchedule: OneToOne → ForeignKey + new fields
        migrations.AddField(
            model_name="backupschedule",
            name="destination",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="schedules",
                to="backups.backupdestination",
            ),
        ),
        migrations.AddField(
            model_name="backupschedule",
            name="keep_daily",
            field=models.PositiveSmallIntegerField(default=7),
        ),
        migrations.AddField(
            model_name="backupschedule",
            name="keep_hourly",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="backupschedule",
            name="keep_monthly",
            field=models.PositiveSmallIntegerField(default=6),
        ),
        migrations.AddField(
            model_name="backupschedule",
            name="keep_weekly",
            field=models.PositiveSmallIntegerField(default=4),
        ),
        migrations.AddField(
            model_name="backupschedule",
            name="minute",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="backupschedule",
            name="name",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="backupschedule",
            name="next_run_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="backupschedule",
            name="frequency",
            field=models.CharField(
                choices=[
                    ("hourly", "Horaire"),
                    ("daily", "Quotidien"),
                    ("weekly", "Hebdomadaire"),
                    ("monthly", "Mensuel"),
                ],
                default="weekly",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="backupschedule",
            name="owner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="backup_schedules",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
